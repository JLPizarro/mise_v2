"""Clientes de AWS reutilizados entre invocaciones y lectura de variables de entorno.

`exigir_entorno` se llama al cargar cada función: si falta una variable, la función falla en el
arranque con un mensaje claro en CloudWatch, en vez de fallar a medias en una petición.
"""

import json
import logging
import os

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from pos_dominio.errores import ErrorDeCodigo, ErrorInfraestructura
from pos_dominio.infra.dynamodb import AlmacenDynamo, normalizar

log = logging.getLogger("pos.aws")
_CONFIG = Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 3, "mode": "standard"})
_clientes: dict = {}
_almacen: AlmacenDynamo | None = None


class VariableFaltante(Exception):
    pass


def exigir_entorno(*nombres: str) -> None:
    faltantes = [n for n in nombres if not os.environ.get(n)]
    if faltantes:
        raise VariableFaltante(f"Faltan variables de entorno: {', '.join(faltantes)}")


def entorno(nombre: str, defecto: str | None = None) -> str:
    valor = os.environ.get(nombre, defecto)
    if valor is None:
        raise ErrorDeCodigo(f"Falta la variable de entorno {nombre}")
    return valor


def cliente(servicio: str):
    if servicio not in _clientes:
        _clientes[servicio] = boto3.client(servicio, config=_CONFIG)
    return _clientes[servicio]


def almacen() -> AlmacenDynamo:
    global _almacen
    if _almacen is None:
        _almacen = AlmacenDynamo()
    return _almacen


def reiniciar() -> None:
    """Para pruebas: olvida clientes creados (moto los necesita dentro de su contexto)."""
    global _almacen
    _clientes.clear()
    _almacen = None


def _llamar(servicio: str, metodo: str, **parametros):
    try:
        return getattr(cliente(servicio), metodo)(**parametros)
    except ClientError as error:
        codigo = error.response.get("Error", {}).get("Code", "")
        raise ErrorInfraestructura(f"{servicio}.{metodo}: {codigo}", causa=codigo) from error
    except BotoCoreError as error:
        raise ErrorInfraestructura(f"{servicio}.{metodo}: {type(error).__name__}", causa="red") from error


def json_texto(datos) -> str:
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"), default=normalizar)


def encolar(url_cola: str, cuerpo: dict, *, grupo: str | None = None, deduplicacion: str | None = None) -> None:
    parametros = {"QueueUrl": url_cola, "MessageBody": json_texto(cuerpo)}
    if grupo:
        parametros["MessageGroupId"] = grupo
    if deduplicacion:
        parametros["MessageDeduplicationId"] = deduplicacion
    _llamar("sqs", "send_message", **parametros)


def cambiar_visibilidad(url_cola: str, recibo: str, segundos: int) -> None:
    _llamar("sqs", "change_message_visibility", QueueUrl=url_cola, ReceiptHandle=recibo,
            VisibilityTimeout=max(0, min(segundos, 43_200)))


def publicar(tema_arn: str, asunto: str, mensaje: str, *, atributos: dict[str, str] | None = None) -> str:
    """Publica en un tema. Los atributos (aviso, tenant_id, local_id, prueba) son los que filtran las
    reglas de distribución de cada destino. Devuelve el MessageId."""
    parametros = {"TopicArn": tema_arn, "Subject": asunto[:100], "Message": mensaje}  # SNS: asunto de hasta 100
    if atributos:
        parametros["MessageAttributes"] = {k: {"DataType": "String", "StringValue": v} for k, v in atributos.items()}
    return _llamar("sns", "publish", **parametros).get("MessageId", "")


def publicar_aviso(aviso_id: str, tenant_id: str, local_id: str, asunto: str, mensaje: str, *,
                   prueba: bool = False) -> str:
    """Publica un aviso en el tema que le asigna el catálogo, con los atributos de sus reglas."""
    from pos_dominio import mensajeria

    canal = mensajeria.canal_de_aviso(aviso_id)
    return publicar(entorno(canal.variable), asunto, mensaje,
                    atributos=mensajeria.atributos_aviso(aviso_id, tenant_id, local_id, prueba=prueba))


def subir(bucket: str, clave: str, contenido: bytes, *, tipo: str, codificacion: str | None = None) -> None:
    parametros = {"Bucket": bucket, "Key": clave, "Body": contenido, "ContentType": tipo}
    if codificacion:
        parametros["ContentEncoding"] = codificacion
    _llamar("s3", "put_object", **parametros)
