"""Entorno de prueba de las funciones: DynamoDB, SQS, SNS y S3 de moto, con las mismas variables de
entorno que define la guía de consola, y constructores de eventos del API Gateway (formato 2.0)."""

import base64
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import boto3
import pytest

from pos_dominio import ids
from pos_dominio.infra import aws, identidad

from conftest import crear_tablas
from integracion.semilla import sembrar

FUNCIONES = Path(__file__).parents[2] / "lambdas" / "funciones"


@dataclass
class Nube:
    dynamo: object
    sqs: object
    s3: object
    sns: object
    cola_dte: str
    cola_contingencia: str
    bucket: str


def _sembrar_mock(dynamo) -> None:
    """Datos de la herramienta `semilla` (los mismos que se cargan en la consola)."""
    spec = importlib.util.spec_from_file_location(
        "herramienta_semilla", Path(__file__).parents[2] / "lambdas" / "herramientas" / "semilla" / "lambda_function.py")
    semilla = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(semilla)
    semilla.sembrar(dynamo, {"configuracion": "configuracion", "operacion": "operacion"})


@pytest.fixture
def nube(monkeypatch):
    yield from _nube(monkeypatch, sembrar)


@pytest.fixture
def nube_mock(monkeypatch):
    yield from _nube(monkeypatch, _sembrar_mock)


def _nube(monkeypatch, sembrador):
    from moto import mock_aws

    with mock_aws():
        dynamo = boto3.client("dynamodb", region_name="us-east-1")
        crear_tablas(dynamo)
        sembrador(dynamo)
        sqs = boto3.client("sqs", region_name="us-east-1")
        cola_dte = sqs.create_queue(QueueName="dte-emision")["QueueUrl"]
        cola_contingencia = sqs.create_queue(QueueName="contingencia-comandas.fifo",
                                             Attributes={"FifoQueue": "true"})["QueueUrl"]
        sqs.create_queue(QueueName="dte-emision-fallidos")
        sqs.create_queue(QueueName="contingencia-comandas-fallidos.fifo", Attributes={"FifoQueue": "true"})
        sns = boto3.client("sns", region_name="us-east-1")
        tema_dueno = sns.create_topic(Name="pos-avisos-dueno")["TopicArn"]
        tema_alertas = sns.create_topic(Name="pos-alertas-tecnicas")["TopicArn"]
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="pos-archivo-pruebas")
        for nombre, valor in {
            "TABLA_OPERACION": "operacion", "TABLA_CONFIGURACION": "configuracion",
            "COLA_DTE_URL": cola_dte, "COLA_CONTINGENCIA_URL": cola_contingencia,
            "TEMA_DUENO_ARN": tema_dueno, "TEMA_ALERTAS_ARN": tema_alertas, "BUCKET_ARCHIVO": "pos-archivo-pruebas",
            "SECRETO_WEBHOOK": "secreto-de-prueba", "DTE_MODO": "ok", "LOG_LEVEL": "WARNING", "ESPERA_SQS_SEGUNDOS": "0",
        }.items():
            monkeypatch.setenv(nombre, valor)
        monkeypatch.delenv("SIMULAR_FALLA_DYNAMODB", raising=False)
        aws.reiniciar()
        identidad.limpiar_cache()
        yield Nube(dynamo, sqs, s3, sns, cola_dte, cola_contingencia, "pos-archivo-pruebas")
        aws.reiniciar()
        identidad.limpiar_cache()


def cargar(nombre: str):
    """Importa lambda_function.py de una función como lo haría Lambda (carpeta con guiones incluida)."""
    ruta = FUNCIONES / nombre / "lambda_function.py"
    modulo = f"funcion_{nombre.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(modulo, ruta)
    funcion = importlib.util.module_from_spec(spec)
    sys.modules[modulo] = funcion
    spec.loader.exec_module(funcion)
    return funcion


def claims(sub: str = "garzon1", **extra) -> dict:
    return {"sub": sub, "email": f"{sub}@demo.cl", "email_verified": "true", "name": sub.capitalize(),
            "iss": "https://accounts.google.com", **extra}


def evento(route_key: str, parametros: dict | None = None, cuerpo=None, *, sub: str | None = "garzon1",
           command_id: str | None = "auto", query: dict | None = None, encabezados: dict | None = None,
           en_base64: bool = False, claims_extra: dict | None = None) -> dict:
    metodo, ruta = route_key.split(" ", 1)
    headers = {"content-type": "application/json", **(encabezados or {})}
    if command_id == "auto" and metodo != "GET":
        command_id = ids.nuevo_ulid()
    if command_id and command_id != "auto":
        headers["x-command-id"] = command_id
    texto = cuerpo if isinstance(cuerpo, (str, bytes)) else (json.dumps(cuerpo) if cuerpo is not None else None)
    if isinstance(texto, str):
        texto = texto.encode("utf-8")
    contexto = {"requestId": f"req-{ids.nuevo_ulid()}", "routeKey": route_key,
                "http": {"method": metodo, "path": ruta, "sourceIp": "203.0.113.10"}}
    if sub:
        contexto["authorizer"] = {"jwt": {"claims": {**claims(sub), **(claims_extra or {})}, "scopes": None}}
    return {
        "version": "2.0", "routeKey": route_key, "rawPath": ruta, "headers": headers,
        "pathParameters": parametros or {}, "queryStringParameters": query, "requestContext": contexto,
        "body": (base64.b64encode(texto).decode() if en_base64 else texto.decode("utf-8")) if texto else None,
        "isBase64Encoded": en_base64,
    }


def cuerpo(respuesta: dict):
    return json.loads(respuesta["body"]) if respuesta.get("body") else None
