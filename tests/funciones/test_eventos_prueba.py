"""eventos-prueba/ está al día y funciona: el flujo de la consola, en orden, sobre los datos de la
herramienta `semilla`, da los códigos HTTP que promete el README."""

import json
import sys
from pathlib import Path

from funciones.utiles import cargar

RAIZ = Path(__file__).parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))

import generar_eventos_prueba as generador  # noqa: E402

EVENTOS = RAIZ / "eventos-prueba"


def test_los_archivos_coinciden_con_el_generador():
    for funcion, nombre, evento, _, _ in generador.FLUJO:
        archivo = EVENTOS / funcion / f"{nombre}.json"
        assert archivo.exists(), f"falta {archivo}; ejecuta scripts/generar_eventos_prueba.py"
        assert json.loads(archivo.read_text(encoding="utf-8")) == json.loads(json.dumps(evento)), archivo
    assert {p.name for p in EVENTOS.iterdir() if p.is_dir()} == {f for f, *_ in generador.FLUJO}


def test_flujo_de_la_consola_sobre_la_semilla(nube_mock):
    funciones = {}
    capturado = {}
    for funcion, nombre, evento, esperado, _ in generador.FLUJO:
        manejador = funciones.setdefault(funcion, cargar(funcion).lambda_handler)
        texto = json.dumps(evento)
        for marcador, valor in capturado.items():
            texto = texto.replace(marcador, valor)
        resultado = manejador(json.loads(texto))
        if esperado is None:
            assert resultado.get("batchItemFailures", []) == [], f"{funcion}/{nombre}: {resultado}"
            continue
        cuerpo = json.loads(resultado["body"]) if resultado.get("body", "").startswith(("{", "[")) else resultado.get("body")
        assert resultado["statusCode"] == esperado, f"{funcion}/{nombre}: {resultado['statusCode']} {cuerpo}"
        if nombre == "01-abrir-turno":
            capturado["REEMPLAZAR_TURNO_ID"] = cuerpo["turno_id"]
        if nombre == "01-consulta-cocina":
            capturado["REEMPLAZAR_TRABAJO_ID"] = cuerpo["jobToken"]
        if nombre == "05-ver-pedido":
            assert cuerpo["total"] == 16500
        if nombre == "10-conteo":
            assert cuerpo["conteo_completado"] is True
        if nombre == "12-cerrar-turno":
            assert cuerpo["diferencia_efectivo"] == 0
        if nombre == "13-conflictos":
            assert [c["codigo_rechazo"] for c in cuerpo["conflictos"]] == ["PEDIDO_CERRADO"]
        if nombre == "02-descargar":
            assert "Pizza napolitana" in cuerpo and "sin aceitunas" in cuerpo


def test_la_semilla_es_idempotente(nube_mock):
    from funciones.utiles import _sembrar_mock
    import boto3

    _sembrar_mock(boto3.client("dynamodb", region_name="us-east-1"))  # segunda vez: no pisa nada
    r = cargar("salon").lambda_handler(json.loads((EVENTOS / "salon" / "03-plano.json").read_text(encoding="utf-8")))
    assert len(json.loads(r["body"])["mesas"]) == 12
