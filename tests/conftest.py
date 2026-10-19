"""Fixtures comunes: tablas `operacion` y `configuracion` en moto, con el mismo esquema que la guía
de consola (PK/SK de texto, índice GSI1, bajo demanda)."""

import os

import boto3
import pytest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "pruebas")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "pruebas")


def crear_tablas(cliente) -> None:
    for nombre in ("operacion", "configuracion"):
        cliente.create_table(
            TableName=nombre,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "GSI1PK", "GSI1SK")],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            GlobalSecondaryIndexes=[{
                "IndexName": "GSI1",
                "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                              {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )


@pytest.fixture
def dynamo():
    from moto import mock_aws

    with mock_aws():
        cliente = boto3.client("dynamodb", region_name="us-east-1")
        crear_tablas(cliente)
        yield cliente


@pytest.fixture
def almacen(dynamo):
    from pos_dominio.infra.dynamodb import AlmacenDynamo

    return AlmacenDynamo(dynamo, dormir=lambda _: None)
