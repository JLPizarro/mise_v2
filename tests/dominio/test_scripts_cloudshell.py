"""Scripts de despliegue por CloudShell: rutas, paquete, JSON generados y sintaxis de bash."""

import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "infra" / "cloudshell"))

import ayudante  # noqa: E402
import paquete_cloudshell  # noqa: E402
import probar_nube  # noqa: E402
import rutas_api  # noqa: E402

ULID = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")


def test_rutas_desde_la_tabla_documentada():
    filas = rutas_api.rutas()
    assert len(filas) == 59
    publicas = {(m, r) for m, r, _, jwt in filas if not jwt}
    assert ("GET", "/salud") in publicas
    assert all(r.startswith(("/salud", "/impresion/", "/publico/", "/webhooks/")) for _, r in publicas)


def test_paquete_con_finales_de_linea_unix_y_scripts_ejecutables(tmp_path):
    destino = paquete_cloudshell.construir(tmp_path / "pos.zip")
    with zipfile.ZipFile(destino) as paquete:
        nombres = set(paquete.namelist())
        for requerido in ("infra/cloudshell/desplegar.sh", "scripts/probar_nube.py", "scripts/construir_capa.py",
                          "docs/migracion/02-api-gateway.md", "lambdas/herramientas/semilla/lambda_function.py",
                          "lambdas/capa/python/pos_dominio/datos/America_Santiago", "infra/athena/eventos.sql",
                          "eventos-prueba/caja/01-abrir-turno.json"):
            assert requerido in nombres, requerido
        script = paquete.getinfo("infra/cloudshell/desplegar.sh")
        assert (script.external_attr >> 16) & 0o111
        assert b"\r\n" not in paquete.read("infra/cloudshell/desplegar.sh")
    assert not any(n.startswith(("tests/", ".venv/", "dist/")) or "__pycache__" in n for n in nombres)


def test_partes_de_texto_rearman_el_mismo_zip(tmp_path):
    destino = paquete_cloudshell.construir(tmp_path / "pos.zip")
    partes = paquete_cloudshell.partir(destino, tmp_path / "partes", lineas_por_parte=1000)
    assert 2 <= len(partes) <= 99
    assert partes[0].name == "pos-parte-01.txt"
    assert [p.name for p in partes] == sorted(p.name for p in partes)
    texto = b"".join(p.read_bytes() for p in partes)
    assert b"\r" not in texto
    import base64
    assert base64.decodebytes(texto) == destino.read_bytes()


def test_json_del_ayudante(tmp_path):
    ayudante.main(["filtro_streams", str(tmp_path / "f.json")])
    filtro = json.loads((tmp_path / "f.json").read_text())
    assert json.loads(filtro["Filters"][0]["Pattern"])["dynamodb"]["Keys"]["SK"]["S"] == [{"prefix": "EVT#"}]
    ayudante.main(["limites_rutas", str(tmp_path / "l.json")])
    limites = json.loads((tmp_path / "l.json").read_text())
    assert len(limites) == 6 and limites["GET /publico/{tenant_id}/{local_id}/reservas/disponibilidad"]["ThrottlingRateLimit"] == 2
    ayudante.main(["atributos", str(tmp_path / "a.json"), "VisibilityTimeout=180",
                   'RedrivePolicy={"deadLetterTargetArn":"arn:x","maxReceiveCount":"5"}'])
    assert json.loads(json.loads((tmp_path / "a.json").read_text())["RedrivePolicy"])["maxReceiveCount"] == "5"


def test_sentencias_de_athena(tmp_path, capsys):
    ayudante.main(["sentencias_sql", str(RAIZ / "infra" / "athena" / "eventos.sql"), "pos-archivo-123", str(tmp_path)])
    assert capsys.readouterr().out.strip() == "2"
    tabla = (tmp_path / "2.sql").read_text()
    assert tabla.startswith("CREATE EXTERNAL TABLE") and "s3://pos-archivo-123/eventos/" in tabla and "<BUCKET" not in tabla


def test_probar_nube_usa_ids_nuevos_y_consistentes():
    prueba = probar_nube.Prueba()
    abrir = prueba.evento("pedidos", "01-abrir-mesa")
    agregar = prueba.evento("pedidos", "02-agregar-pizza-xl")
    pedido = json.loads(abrir["body"])["pedido_id"]
    assert ULID.match(pedido) and not pedido.startswith("01K7H0Z3Q8")
    assert agregar["pathParameters"]["pedido_id"] == pedido
    assert agregar["headers"]["x-command-id"] != abrir["headers"]["x-command-id"]
    sector = json.loads(prueba.evento("administracion", "02-crear-sector")["body"])["nombre"]
    assert sector.startswith("Barra exterior ") and sector != "Barra exterior"


def _bash() -> str | None:
    """Un bash que funcione. En Windows, `bash` suele ser el lanzador de WSL sin distribución: se
    prefiere el de Git for Windows."""
    candidatos = [r"C:\Program Files\Gitinash.exe", shutil.which("bash")]
    for candidato in candidatos:
        if candidato and Path(candidato).exists():
            try:
                if subprocess.run([candidato, "-c", "true"], capture_output=True, timeout=20).returncode == 0:
                    return candidato
            except (OSError, subprocess.TimeoutExpired):
                continue
    return None


BASH = _bash()


@pytest.mark.skipif(BASH is None, reason="no hay un bash funcional")
@pytest.mark.parametrize("script", ["desplegar.sh", "configurar_google.sh", "publicar_pwa.sh", "revertir.sh", "simulacro.sh"])
def test_sintaxis_bash(script):
    subprocess.run([BASH, "-n", str(RAIZ / "infra" / "cloudshell" / script)], check=True)
