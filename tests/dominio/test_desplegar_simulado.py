"""Ejecuta infra/cloudshell/desplegar.sh completo contra una AWS CLI falsa (tests/herramientas/aws_falso.py).

No reemplaza probarlo en AWS, pero detecta lo que más rompe estos scripts: variables sin definir,
errores de bash, JSON mal armado y rutas o funciones que faltan. Dos escenarios: primer despliegue
(todo se crea) y re-ejecución (todo existe y se actualiza).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).parents[2]


def _bash() -> str | None:
    for candidato in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if candidato and Path(candidato).exists():
            try:
                if subprocess.run([candidato, "-c", "true"], capture_output=True, timeout=20).returncode == 0:
                    return candidato
            except (OSError, subprocess.TimeoutExpired):
                continue
    return None


BASH = _bash()


def _posix(ruta: Path) -> str:
    return str(ruta).replace("\\", "/")


def _msys(ruta: Path) -> str:
    """C:/x -> /c/x: en PATH, bash separa por ':' y rompería la letra de unidad."""
    texto = _posix(ruta)
    return f"/{texto[0].lower()}{texto[2:]}" if len(texto) > 1 and texto[1] == ":" else texto


def _pwa_falsa(destino: Path) -> Path:
    """Una compilación mínima de la PWA, con la misma forma que pwa/dist."""
    (destino / "assets").mkdir(parents=True)
    for nombre, contenido in {
        "index.html": "<!doctype html>", "sw.js": "const VERSION = 'x'", "precache.json": '{"archivos": []}',
        "manifest.webmanifest": "{}", "favicon.svg": "<svg/>", "config.json": '{"api_url": "http://localhost:8001"}',
        "assets/index-abc123.js": "1", "assets/index-abc123.css": "1",
    }.items():
        (destino / nombre).write_text(contenido, encoding="utf-8")
    return destino


def ejecutar(tmp_path: Path, existe: bool, con_pwa: bool = False, cliente_google: str = "") -> tuple[list[list[str]], str]:
    shims = tmp_path / "bin"
    shims.mkdir()
    python = _posix(Path(sys.executable))
    falso = _posix(RAIZ / "tests/herramientas/aws_falso.py")
    (shims / "aws").write_text(f'#!/usr/bin/env bash\nexec "{python}" "{falso}" "$@"\n', encoding="utf-8", newline="\n")
    (shims / "python3").write_text(f'#!/usr/bin/env bash\nexec "{python}" "$@"\n', encoding="utf-8", newline="\n")
    for shim in shims.iterdir():
        shim.chmod(0o755)
    log = tmp_path / "llamadas.jsonl"
    # Sin pwa, PWA_DIST apunta a una carpeta que no existe: el resultado no depende de si hay un pwa/dist real.
    dist = _pwa_falsa(tmp_path / "pwa-dist") if con_pwa else tmp_path / "sin-pwa"
    entorno = {**os.environ, "AWS_FALSO_LOG": _posix(log), "AWS_FALSO_EXISTE": "1" if existe else "0",
               "POS_TMP": _posix(tmp_path / "trabajo"), "MSYS_NO_PATHCONV": "1", "EMAIL_AVISOS": "equipo@ejemplo.cl",
               "EMAIL_DUENO_REAL": "dueno@ejemplo.cl", "AWS_FALSO_SIN_GSI": "1" if existe else "0",
               "PWA_DIST": _posix(dist), "AWS_FALSO_COPIAS": _posix(tmp_path / "copias"), "GOOGLE_CLIENT_ID": cliente_google}
    comando = f'export PATH="{_msys(shims)}:$PATH"; bash infra/cloudshell/desplegar.sh'
    proceso = subprocess.run([BASH, "-c", comando], cwd=RAIZ, env=entorno, capture_output=True, text=True,
                             encoding="utf-8", timeout=600)
    assert proceso.returncode == 0, proceso.stdout[-3000:] + proceso.stderr[-3000:]
    assert "==> Listo" in proceso.stdout
    return [json.loads(linea) for linea in log.read_text(encoding="utf-8").splitlines()], proceso.stdout


def desplegar(tmp_path: Path, existe: bool) -> list[list[str]]:
    return ejecutar(tmp_path, existe)[0]


def _contar(llamadas, servicio, orden):
    return sum(1 for a in llamadas if a[:2] == [servicio, orden])


@pytest.mark.skipif(BASH is None, reason="no hay un bash funcional")
def test_primer_despliegue_crea_todo(tmp_path):
    llamadas = desplegar(tmp_path, existe=False)
    assert _contar(llamadas, "dynamodb", "create-table") == 2
    assert _contar(llamadas, "sqs", "create-queue") == 5
    # Las colas salen del catálogo central, con su cola de fallidos y número de recepciones.
    dte = next(a for a in llamadas if a[:2] == ["sqs", "create-queue"] and "dte-emision" in a)
    assert "dte-emision" in dte
    assert _contar(llamadas, "lambda", "create-function") == 15  # 14 + semilla
    assert _contar(llamadas, "lambda", "create-alias") == 14
    assert _contar(llamadas, "lambda", "create-event-source-mapping") == 3
    assert _contar(llamadas, "apigatewayv2", "create-integration") == 10
    assert _contar(llamadas, "apigatewayv2", "create-route") == 59
    assert _contar(llamadas, "apigatewayv2", "create-deployment") == 1
    assert _contar(llamadas, "cloudwatch", "put-metric-alarm") == 9
    assert _contar(llamadas, "athena", "start-query-execution") == 2
    salud = next(a for a in llamadas if a[:2] == ["apigatewayv2", "create-route"] and "GET /salud" in a)
    assert salud[salud.index("--authorization-type") + 1] == "NONE"
    privada = next(a for a in llamadas if a[:2] == ["apigatewayv2", "create-route"] and "GET /yo" in a)
    assert privada[privada.index("--authorization-type") + 1] == "JWT" and "--authorizer-id" in privada
    autorizador = next(a for a in llamadas if a[:2] == ["apigatewayv2", "create-authorizer"])
    assert "$request.header.Authorization" in autorizador
    streams = next(a for a in llamadas if a[:2] == ["lambda", "create-event-source-mapping"] and "procesador-eventos:vivo" in a)
    for opcion in ("--bisect-batch-on-function-error", "--filter-criteria", "--destination-config"):
        assert opcion in streams
    assert "ReportBatchItemFailures" in streams
    assert any(a[:2] == ["lambda", "delete-function"] and "semilla" in a for a in llamadas)
    valores = (RAIZ / "valores-despliegue.env").read_text(encoding="utf-8")
    assert 'URL_API="https://abc123.execute-api.us-east-1.amazonaws.com/prod"' in valores


@pytest.mark.skipif(BASH is None, reason="no hay un bash funcional")
def test_reejecucion_actualiza_sin_duplicar(tmp_path):
    llamadas = desplegar(tmp_path, existe=True)
    assert _contar(llamadas, "dynamodb", "create-table") == 0
    assert _contar(llamadas, "lambda", "create-function") == 1  # solo la semilla temporal
    assert _contar(llamadas, "lambda", "update-function-code") == 14
    assert _contar(llamadas, "lambda", "update-alias") == 14
    assert _contar(llamadas, "lambda", "create-event-source-mapping") == 0
    assert _contar(llamadas, "apigatewayv2", "create-route") == 0
    assert _contar(llamadas, "apigatewayv2", "update-route") == 59
    assert _contar(llamadas, "apigatewayv2", "update-authorizer") == 0  # sin GOOGLE_CLIENT_ID no se toca
    # Tablas que ya existían sin GSI1 (creadas a mano): el índice se agrega con su proyección.
    indices = [a for a in llamadas if a[:2] == ["dynamodb", "update-table"] and "--global-secondary-index-updates" in a]
    assert sorted(a[a.index("--table-name") + 1] for a in indices) == ["configuracion", "operacion"]
    secreto = next(a for a in llamadas if a[:2] == ["lambda", "update-function-configuration"] and "pedidos-externos" in a)
    entorno = secreto[secreto.index("--environment") + 1]
    assert entorno.startswith("file://")


def _subidas_pwa(llamadas):
    return [a for a in llamadas if a[:2] in (["s3", "sync"], ["s3", "cp"]) and "obtener_token.html" not in " ".join(a)]


@pytest.mark.skipif(BASH is None, reason="no hay un bash funcional")
def test_sin_pwa_no_publica_nada_y_lo_dice(tmp_path):
    llamadas, salida = ejecutar(tmp_path, existe=False)
    assert _subidas_pwa(llamadas) == []
    assert "15. PWA" not in salida and "PWA:           (no publicada" in salida


@pytest.mark.skipif(BASH is None, reason="no hay un bash funcional")
def test_con_pwa_la_publica_en_orden_y_con_el_config_de_la_nube(tmp_path):
    llamadas, salida = ejecutar(tmp_path, existe=False, con_pwa=True, cliente_google="123.apps.googleusercontent.com")
    subidas = _subidas_pwa(llamadas)
    destinos = [a for a in subidas]
    assert all("--delete" not in a for a in subidas)

    def cache(a):
        return a[a.index("--cache-control") + 1]

    # 1. assets inmutables; 2. el resto estático; 3. lo que se revalida; 4. index.html al final.
    assert destinos[0][:2] == ["s3", "sync"] and destinos[0][2].endswith("/assets")
    assert cache(destinos[0]) == "public,max-age=31536000,immutable"
    assert destinos[1][:2] == ["s3", "sync"] and cache(destinos[1]) == "public,max-age=86400"
    for excluido in ("config.json", "index.html", "sw.js", "precache.json", "manifest.webmanifest"):
        assert excluido in destinos[1]
    claves = [a[3].split("/", 3)[3] for a in destinos[2:]]
    assert claves == ["manifest.webmanifest", "sw.js", "precache.json", "config.json", "index.html"]
    assert all(cache(a) == "no-cache" for a in destinos[2:])
    tipos = {a[3].split("/", 3)[3]: a[a.index("--content-type") + 1] for a in destinos[2:]}
    assert tipos["manifest.webmanifest"] == "application/manifest+json"
    assert tipos["sw.js"] == "text/javascript" and tipos["precache.json"] == "application/json"
    assert tipos["index.html"] == "text/html; charset=utf-8"
    # El config.json sale de un directorio temporal, nunca de pwa/dist, y apunta al API de la nube.
    config = next(a for a in destinos if a[3].endswith("/config.json"))
    assert "pwa-dist" not in config[2]
    assert json.loads((tmp_path / "copias" / "config.json").read_text(encoding="utf-8")) == {
        "api_url": "https://abc123.execute-api.us-east-1.amazonaws.com/prod",
        "google_client_id": "123.apps.googleusercontent.com", "modo_dev": False}
    assert "PWA: https://pos-sitio-123456789012.s3.us-east-1.amazonaws.com/index.html" in salida
    valores = (RAIZ / "valores-despliegue.env").read_text(encoding="utf-8")
    assert 'GOOGLE_CLIENT_ID="123.apps.googleusercontent.com"' in valores


@pytest.mark.skipif(BASH is None, reason="no hay un bash funcional")
def test_reejecucion_con_pwa_tambien_pasa(tmp_path):
    llamadas, _ = ejecutar(tmp_path, existe=True, con_pwa=True)
    assert len(_subidas_pwa(llamadas)) == 7
