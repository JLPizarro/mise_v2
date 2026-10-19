"""Arma los .zip para subir desde la consola de Lambda.

Solo biblioteca estándar. Uso, desde la raíz del repositorio:

    python scripts/construir_capa.py

Produce:
  dist/capa-pos-dominio.zip           capa con la estructura python/pos_dominio/...
  dist/funciones/<nombre>.zip         una por función, con lambda_function.py en la raíz
  dist/herramientas/semilla.zip       herramienta temporal que carga los datos mock

Sin la carpeta `python/` en la raíz del .zip de la capa, las funciones fallan con
"No module named 'pos_dominio'". Cada función también se puede pegar a mano en el editor de la
consola: su código es un solo archivo, lambdas/funciones/<nombre>/lambda_function.py.
"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / "lambdas" / "capa"
FUNCIONES = RAIZ / "lambdas" / "funciones"
DESTINO = RAIZ / "dist" / "capa-pos-dominio.zip"
# Fecha fija para que el mismo código produzca el mismo .zip (mismo SHA-256).
_FECHA = (2026, 1, 1, 0, 0, 0)


def archivos() -> list[Path]:
    return sorted(p for p in (ORIGEN / "python").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")


def _escribir(zip_destino: zipfile.ZipFile, ruta: str, contenido: bytes) -> None:
    info = zipfile.ZipInfo(ruta, date_time=_FECHA)
    info.external_attr = 0o644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    zip_destino.writestr(info, contenido)


def construir(destino: Path = DESTINO) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as zip_capa:
        for archivo in archivos():
            _escribir(zip_capa, archivo.relative_to(ORIGEN).as_posix(), archivo.read_bytes())
    return destino


def construir_funciones(destino: Path = RAIZ / "dist" / "funciones", origen: Path = FUNCIONES) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    zips = []
    for carpeta in sorted(p for p in origen.iterdir() if (p / "lambda_function.py").is_file()):
        ruta_zip = destino / f"{carpeta.name}.zip"
        with zipfile.ZipFile(ruta_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_funcion:
            _escribir(zip_funcion, "lambda_function.py", (carpeta / "lambda_function.py").read_bytes())
        zips.append(ruta_zip)
    return zips


def _huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]


def main() -> int:
    destino = construir()
    with zipfile.ZipFile(destino) as zip_capa:
        nombres = zip_capa.namelist()
    if "python/pos_dominio/__init__.py" not in nombres:
        print("ERROR: el .zip no tiene python/pos_dominio/__init__.py", file=sys.stderr)
        return 1
    print(f"{destino.relative_to(RAIZ)}  {len(nombres)} archivos  {destino.stat().st_size} bytes  sha256 {_huella(destino)}")
    for ruta_zip in construir_funciones() + construir_funciones(RAIZ / "dist" / "herramientas",
                                                                RAIZ / "lambdas" / "herramientas"):
        print(f"{ruta_zip.relative_to(RAIZ)}  sha256 {_huella(ruta_zip)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
