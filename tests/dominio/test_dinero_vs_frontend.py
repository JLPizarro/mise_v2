"""El dominio nuevo contra los valores de referencia del frontend actual (golden.json).

golden.json se genera con tests/caracterizacion/frontend/reglas_caja.mjs, transcripción literal de
las funciones de PendientesCaja.tsx y FormularioPago.tsx. Cada diferencia es intencional y lleva
su código del inventario.
"""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from pos_dominio import dinero
from pos_dominio.errores import Validacion

DIR = Path(__file__).parents[1] / "caracterizacion" / "frontend"
GOLDEN = json.loads((DIR / "golden.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_golden_coincide_con_la_transcripcion():
    salida = subprocess.run(["node", str(DIR / "reglas_caja.mjs")], capture_output=True, text=True, check=True)
    assert json.loads(salida.stdout) == GOLDEN


@pytest.mark.parametrize("caso", GOLDEN["propina_sugerida"], ids=lambda c: f"{c['monto']}x{c['pct']}")
def test_propina_sugerida_redondea_igual_que_el_frontend(caso):
    assert dinero.propina_sugerida(caso["monto"], caso["pct"]) == caso["propina"]


def test_propina_no_usa_el_redondeo_al_par_de_python():
    assert round(1005 * 10 / 100) == 100          # lo que daría Python
    assert dinero.propina_sugerida(1005, 10) == 101  # lo que mostraba el POS local


def test_propina_entera_equivale_a_math_round_en_todo_el_rango():
    # Math.round(x) = floor(x + 0.5) para x >= 0
    for monto in range(0, 200_001):
        for pct in (5, 10, 12, 15):
            assert dinero.propina_sugerida(monto, pct) == math.floor(monto * pct / 100 + 0.5), (monto, pct)


@pytest.mark.parametrize("caso", GOLDEN["division_igual"], ids=lambda c: f"{c['total']}/{c['n']}")
def test_partes_iguales(caso):
    if caso["total"] < caso["n"]:
        # D22: el local creaba partes de $0 que después no se podían cobrar.
        assert 0 in caso["partes"]
        with pytest.raises(Validacion) as error:
            dinero.dividir_partes_iguales(caso["total"], caso["n"])
        assert error.value.codigo == "PARTE_EN_CERO"
    else:
        assert dinero.dividir_partes_iguales(caso["total"], caso["n"]) == caso["partes"]


@pytest.mark.parametrize("personas", [1, 21])
def test_partes_iguales_respeta_el_rango_de_la_pantalla(personas):
    with pytest.raises(Validacion):
        dinero.dividir_partes_iguales(10_000, personas)


ITEMS = {"a": (3, 1500), "b": (1, 10000), "c": (2, 999)}  # (cantidad, precio congelado) de golden


def _disponibles(pagos):
    cobradas = {}
    for pago in pagos:
        if pago["tipo_division"] == "items":
            for ic in pago["items_cobrados"]:
                cobradas[ic["item_id"]] = cobradas.get(ic["item_id"], 0) + ic["cantidad"]
    return {k: (cant - cobradas.get(k, 0), precio) for k, (cant, precio) in ITEMS.items()}


@pytest.mark.parametrize("caso", GOLDEN["seleccion_items"], ids=lambda c: json.dumps(c["seleccion"]))
def test_monto_por_items(caso):
    esperado = caso["resultado"]
    pares = [(s["item_id"], s["cantidad"]) for s in caso["seleccion"]]
    if esperado is None:
        # El frontend descarta ítems ajenos o en cero; el servidor nuevo los rechaza antes
        # (ITEM_AJENO, cantidad mínima 1), así que aquí no hay monto que comparar.
        return
    seleccion = dinero.agrupar_seleccion(pares)
    disponibles = _disponibles(caso["pagos"])
    repetidos = len(pares) != len(seleccion)
    if repetidos:
        # D23: con el ítem repetido el frontend cobraba 4 unidades de un ítem de 3.
        with pytest.raises(Validacion) as error:
            dinero.monto_por_items(disponibles, seleccion, caso["saldo"])
        assert error.value.codigo == "ITEM_SIN_UNIDADES"
        return
    if any(c > disponibles[i][0] for i, c in seleccion.items()):
        # El frontend recortaba en silencio la cantidad a lo disponible; el servidor la rechaza.
        with pytest.raises(Validacion):
            dinero.monto_por_items(disponibles, seleccion, caso["saldo"])
        recortada = {i: min(c, disponibles[i][0]) for i, c in seleccion.items()}
        assert dinero.monto_por_items(disponibles, recortada, caso["saldo"]) == esperado["monto"]
        return
    assert dinero.monto_por_items(disponibles, seleccion, caso["saldo"]) == esperado["monto"]


def test_D24_la_vista_previa_del_frontend_usaba_el_precio_del_catalogo():
    distintos = [c for c in GOLDEN["vista_previa_items"] if c["precio_congelado"] != c["precio_vista_previa"]]
    assert distintos, "la diferencia que justifica D24 ya no está en el golden"
    # El dominio cobra siempre el precio congelado.
    assert dinero.monto_por_items({"a": (3, 1500)}, {"a": 1}, 99_999) == 1500


@pytest.mark.parametrize("caso", [c for c in GOLDEN["formulario_pago"] if c["mixto"] and len(c["medios"]) == 2],
                         ids=lambda c: json.dumps([m["monto"] for m in c["medios"]]))
def test_en_pago_mixto_el_ultimo_medio_cubre_el_resto(caso):
    previo = int(caso["medios"][0]["monto"] or 0)
    assert dinero.completar_ultimo_medio(caso["total"], [previo]) == caso["resultado"]["pagos"][1]["monto"]
