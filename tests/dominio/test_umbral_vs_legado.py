"""Umbral del arqueo: el dominio nuevo (puntos base, aritmética exacta) contra el código local."""

import pytest

from app.application.use_cases.caja_use_cases import calcular_umbral_diferencia as umbral_legado

from pos_dominio import dinero


@pytest.mark.parametrize("pct,pb", [(2.0, 200), (2.5, 250), (1.0, 100), (5.0, 500), (0.5, 50), (10.0, 1000)])
@pytest.mark.parametrize("minimo", [0, 5000])
def test_mismo_umbral_que_el_local_con_porcentajes_exactos(pct, pb, minimo):
    for esperado in range(0, 2_000_001, 997):
        assert dinero.umbral_diferencia(esperado, pb, minimo) == umbral_legado(esperado, pct, minimo), esperado


def test_mismo_umbral_en_los_casos_de_mitad_exacta():
    for esperado in (250_025, 250_075, 125_025, 1_000_050, 75):
        assert dinero.umbral_diferencia(esperado, 200, 0) == umbral_legado(esperado, 2.0, 0)


def test_sin_diferencias_con_porcentajes_no_representables_en_binario():
    """1,75 %, 3,33 % o 2,15 % no son exactos en float. Aun así, en todo este rango el local y el
    dominio nuevo dan el mismo umbral, así que el paso a puntos base no cambia resultados."""
    cambios = [(pct, esperado)
               for pct, pb in ((1.75, 175), (3.33, 333), (2.15, 215))
               for esperado in range(0, 300_001)
               if dinero.umbral_diferencia(esperado, pb, 0) != umbral_legado(esperado, pct, 0)]
    assert cambios == []
