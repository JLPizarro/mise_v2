"""Servidor local de desarrollo (scripts/servidor_local.py): emula el API Gateway con las Lambdas reales."""

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("moto")

RAIZ = Path(__file__).parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))

import servidor_local  # noqa: E402
from validar_despliegue import ulid  # noqa: E402

ORIGEN = "http://localhost:8000"


@pytest.fixture(scope="module")
def api():
    servidor = servidor_local.crear_servidor(0, ORIGEN)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}"
    finally:
        servidor.shutdown()
        hilo.join(timeout=10)
        servidor.cerrar_todo()


def llamar(api, metodo, ruta, cuerpo=None, *, sub=None, command_id=None):
    cabeceras = {"content-type": "application/json"}
    if sub:
        cabeceras["authorization"] = f"Bearer dev:{sub}"
    if command_id:
        cabeceras["x-command-id"] = command_id
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(api + ruta, data=datos, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            texto = r.read().decode()
            return r.status, (json.loads(texto) if texto else None), dict(r.headers)
    except urllib.error.HTTPError as error:
        texto = error.read().decode()
        return error.code, (json.loads(texto) if texto else None), dict(error.headers)


def test_salud_responde_200(api):
    estado, cuerpo, _ = llamar(api, "GET", "/salud")
    assert estado == 200
    assert cuerpo["estado"] == "ok"


def test_options_devuelve_los_encabezados_cors(api):
    estado, _, cabeceras = llamar(api, "OPTIONS", "/locales/local_01/salon")
    assert estado == 204
    assert cabeceras["Access-Control-Allow-Origin"] == ORIGEN
    assert cabeceras["Access-Control-Allow-Headers"] == "authorization,content-type,x-command-id"
    assert cabeceras["Access-Control-Allow-Methods"] == "GET,POST,PATCH,DELETE"
    assert cabeceras["Access-Control-Max-Age"] == "600"


def test_yo_exige_token_de_desarrollo(api):
    estado, cuerpo, _ = llamar(api, "GET", "/yo")
    assert (estado, cuerpo) == (401, {"message": "Unauthorized"})
    estado, cuerpo, cabeceras = llamar(api, "GET", "/yo", sub="mock-cajero")
    assert estado == 200
    assert [x["local_id"] for x in cuerpo["locales"]] == ["local_01"]
    assert cabeceras["Access-Control-Allow-Origin"] == ORIGEN


def test_ruta_inexistente_responde_404(api):
    assert llamar(api, "GET", "/no-existe")[:2] == (404, {"message": "Not Found"})


def test_abrir_una_mesa_con_command_id_responde_201(api):
    estado, pedido, _ = llamar(api, "POST", "/locales/local_01/pedidos", {"mesa_id": "m03", "pedido_id": (propuesto := ulid())},
                               sub="mock-garzon", command_id=ulid())
    assert estado == 201
    assert pedido["pedido_id"] == propuesto


def test_contingencia_con_las_rutas_normales_caidas(api):
    garzon = {"sub": "mock-garzon"}
    mesa, pedido, item = "m05", ulid(), ulid()
    assert llamar(api, "POST", "/locales/local_01/pedidos", {"mesa_id": mesa, "pedido_id": pedido}, command_id=ulid(), **garzon)[0] == 201

    assert llamar(api, "POST", "/__dev/fallas", {"rutas_normales": True})[0] == 200
    try:
        cuerpo = {"pedido_id": pedido, "mesa_id": mesa, "item_id": item, "producto_id": "pizza", "cantidad": 1}
        comando = ulid()
        ruta = f"/locales/local_01/pedidos/{pedido}/items"
        assert llamar(api, "POST", ruta, cuerpo, command_id=comando, **garzon)[:2] == (503, {"message": "Service Unavailable"})

        estado, respuesta, _ = llamar(api, "POST", "/contingencia/comandas", {
            "operacion": "pedido.agregar_item", "local_id": "local_01", "cuerpo": cuerpo,
            "ocurrido_en": "2026-01-01T12:00:00Z"}, command_id=comando, **garzon)
        assert estado == 202
        assert respuesta["estado"] == "aceptada_en_contingencia"
    finally:
        llamar(api, "POST", "/__dev/fallas", {"rutas_normales": False})

    estado, datos, _ = llamar(api, "GET", f"/locales/local_01/pedidos/{pedido}", **garzon)
    assert estado == 200
    assert [i["item_id"] for i in datos["items"]] == [item]
