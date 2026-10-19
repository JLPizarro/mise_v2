"""Registro de mensajes que un consumidor no pudo procesar.

Cada intento fallido deja un ítem en `operacion` (PK = <local>#FALLOS, 14 días de vida) con el
consumidor, el canal, el identificador del mensaje, el número de intento, el error y su **origen**.
Así, cuando un mensaje termina en una cola de fallidos, el panel de Administración → Mensajería
muestra por qué y a quién le corresponde resolverlo.

Origen (lo decide `clasificar` según el tipo de error, nunca el texto):
- `proveedor`: un servicio externo no respondió (proveedor de documentos caído, lento o saturado).
  Hay que esperar o hablar con el proveedor.
- `aws`: falló un servicio de AWS propio (DynamoDB, SQS, SNS, S3) o la red hacia él. Lo revisa el
  equipo técnico.
- `negocio`: una regla del negocio rechazó la operación (por ejemplo, la mesa ya estaba cobrada).
- `codigo`: un defecto del propio sistema (dato con formato inesperado, error no previsto).

Es de mejor esfuerzo: si DynamoDB es justo lo que está fallando, el registro tampoco se guarda y el
diagnóstico queda solo en CloudWatch Logs (con el mismo mensaje_id). Nunca hace fallar al consumidor.
"""

import logging
import os

from botocore.exceptions import BotoCoreError, ClientError

from pos_dominio import claves, tiempo
from pos_dominio.dte import ErrorProveedor
from pos_dominio.errores import ErrorDominio, ErrorInfraestructura
from pos_dominio.infra import aws
from pos_dominio.infra.dynamodb import a_item

log = logging.getLogger("pos.fallos")
DIAS_DE_VIDA = 14
_MAX_TEXTO = 300
ORIGENES = ("proveedor", "aws", "negocio", "codigo")


def clasificar(error: BaseException) -> str:
    if isinstance(error, ErrorProveedor):
        return "proveedor"
    if isinstance(error, (ErrorInfraestructura, ClientError, BotoCoreError)):
        return "aws"
    if isinstance(error, ErrorDominio):
        return "negocio"
    return "codigo"


def registrar(*, consumidor: str, canal: str, mensaje_id: str, intento: int, error: BaseException,
              tenant_id: str | None, local_id: str | None, referencia: str = "", recuperable: bool = True,
              mensaje: str | None = None) -> None:
    """`mensaje` reemplaza el texto del error por uno más claro para quien lo lee en el panel."""
    if not tenant_id or not local_id or not mensaje_id:
        log.warning("fallo sin local identificable: queda solo en el log",
                    extra={"consumidor": consumidor, "canal": canal, "mensaje_id": mensaje_id})
        return
    ahora = tiempo.ahora_utc()
    texto = " ".join((mensaje if mensaje is not None else str(error)).split())[:_MAX_TEXTO]
    item = {
        "PK": claves.fallos(claves.local(tenant_id, local_id)),
        "SK": f"FALLO#{tiempo.iso(ahora)}#{mensaje_id}",
        "tipo_item": "FALLO", "consumidor": consumidor, "canal": canal, "mensaje_id": mensaje_id,
        "intento": int(intento), "origen": clasificar(error), "error_tipo": type(error).__name__,
        "error_mensaje": texto, "referencia": referencia, "recuperable": recuperable,
        "registrado_en": tiempo.iso(ahora), "expira_en": tiempo.epoch(ahora) + DIAS_DE_VIDA * 86_400,
    }
    try:
        aws.cliente("dynamodb").put_item(TableName=os.environ["TABLA_OPERACION"], Item=a_item(item))
    except Exception:  # noqa: BLE001 - el registro nunca debe tumbar al consumidor
        log.warning("no se pudo guardar el registro del fallo", extra={"mensaje_id": mensaje_id})
