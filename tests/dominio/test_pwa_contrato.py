"""Contrato entre la PWA y las Lambdas: las rutas y las operaciones de comanda que usa el código de
`pwa/src/api` son las que existen en el backend congelado."""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))

import rutas_api  # noqa: E402
from pos_dominio.operaciones import pedidos  # noqa: E402

RUTAS_TS = RAIZ / "pwa" / "src" / "api" / "rutas.ts"
COMANDOS_TS = RAIZ / "pwa" / "src" / "api" / "comandos.ts"
_RUTA = re.compile(r'"(GET|POST|PATCH|DELETE) (/[^"]*)"')


def _rutas_usadas() -> list[tuple[str, str]]:
    return _RUTA.findall(RUTAS_TS.read_text(encoding="utf-8"))


def test_cada_ruta_usada_existe_en_la_tabla_de_rutas():
    existentes = {(metodo, ruta) for metodo, ruta, _, _ in rutas_api.rutas()}
    usadas = _rutas_usadas()
    assert len(usadas) > 30
    assert not [r for r in usadas if r not in existentes]


def test_la_pwa_no_usa_rutas_de_impresoras_reservas_ni_webhooks():
    prohibidas = [r for _, r in _rutas_usadas() if r.startswith(("/impresion/", "/publico/", "/webhooks/"))]
    assert prohibidas == []


def test_las_operaciones_de_comanda_son_las_de_contingencia():
    texto = COMANDOS_TS.read_text(encoding="utf-8")
    bloque = re.search(r"OPERACIONES_COMANDA = \[(.*?)\] as const", texto, re.DOTALL).group(1)
    assert set(re.findall(r'"([a-z_.]+)"', bloque)) == set(pedidos.CONTINGENCIA)
