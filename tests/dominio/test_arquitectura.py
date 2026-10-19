"""Reglas de arquitectura de la capa: el dominio no depende de boto3 ni de bibliotecas externas."""

import ast
import sys
from pathlib import Path

CAPA = Path(__file__).parents[2] / "lambdas" / "capa" / "python" / "pos_dominio"
PERMITIDOS_EN_INFRA = {"boto3", "botocore"}


def _modulos_importados(archivo: Path) -> set[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    modulos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
            modulos.add(nodo.module)
    return modulos


def _importaciones(archivo: Path) -> set[str]:
    return {m.split(".")[0] for m in _modulos_importados(archivo)}


def test_solo_biblioteca_estandar_boto3_y_el_propio_paquete():
    for archivo in CAPA.rglob("*.py"):
        externos = _importaciones(archivo) - set(sys.stdlib_module_names) - {"pos_dominio"}
        if "infra" in archivo.parts:
            externos -= PERMITIDOS_EN_INFRA
        assert not externos, f"{archivo.relative_to(CAPA)} importa {externos}"


def test_el_dominio_no_importa_infraestructura():
    for archivo in CAPA.rglob("*.py"):
        if "infra" in archivo.parts:
            continue
        modulos = _modulos_importados(archivo)
        assert not any(m.startswith("pos_dominio.infra") for m in modulos), archivo.relative_to(CAPA)
        assert not {"boto3", "botocore"} & _importaciones(archivo), archivo.relative_to(CAPA)


def test_la_zona_horaria_de_respaldo_viene_en_la_capa():
    from zoneinfo import ZoneInfo

    with open(CAPA / "datos" / "America_Santiago", "rb") as archivo:
        assert ZoneInfo.from_file(archivo, key="America/Santiago").utcoffset(None) is None
