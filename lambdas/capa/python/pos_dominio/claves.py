"""Claves de las tablas `configuracion` y `operacion` (docs/migracion/01-modelo-dynamodb.md §4).

Solo construye cadenas; no importa boto3. Todo identificador se valida antes de entrar en una
clave para que nadie pueda inyectar `#` y apuntar a la partición de otro cliente.
"""

import re

from pos_dominio.errores import Validacion

TABLA_CONFIGURACION = "configuracion"
TABLA_OPERACION = "operacion"

_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_EMAIL = re.compile(r"^[^\s#@]+@[^\s#@]+\.[^\s#@]+$")


def validar_id(valor, campo: str = "id") -> str:
    if not isinstance(valor, str) or not _ID.match(valor):
        raise Validacion(f"{campo} inválido", codigo="ID_INVALIDO", detalle={"campo": campo})
    return valor


def normalizar_email(valor) -> str:
    if not isinstance(valor, str) or not _EMAIL.match(valor.strip()):
        raise Validacion("email inválido", codigo="EMAIL_INVALIDO")
    return valor.strip().lower()


def local(tenant_id: str, local_id: str) -> str:
    return f"TENANT#{validar_id(tenant_id, 'tenant_id')}#LOCAL#{validar_id(local_id, 'local_id')}"


def tenant(tenant_id: str) -> str:
    return f"TENANT#{validar_id(tenant_id, 'tenant_id')}"


# --- configuracion -------------------------------------------------------------------------------

def usuario(sub: str) -> str:
    return f"USER#{validar_id(sub, 'sub')}"


def invitacion(email: str) -> str:
    return f"INVITACION#{normalizar_email(email)}"


def sk_membresia(tenant_id: str, local_id: str) -> str:
    return f"MEMBRESIA#{validar_id(tenant_id, 'tenant_id')}#{validar_id(local_id, 'local_id')}"


def email(email: str) -> str:
    """Identidad: email -> sub, creado en el primer ingreso. Permite invitar a una persona que ya
    usa la plataforma en otro local sin esperar a que vuelva a ingresar."""
    return f"EMAIL#{normalizar_email(email)}"


def gsi_personal(L: str) -> str:
    return f"{L}#PERSONAL"


def sk_mesa(mesa_id: str) -> str:
    return f"MESA#{validar_id(mesa_id, 'mesa_id')}"


def sk_producto(producto_id: str) -> str:
    return f"PROD#{validar_id(producto_id, 'producto_id')}"


def sk_cuarto(cuarto_id: str) -> str:
    return f"CUARTO#{validar_id(cuarto_id, 'cuarto_id')}"


def sk_impresora(impresora_id: str) -> str:
    return f"IMPRESORA#{validar_id(impresora_id, 'impresora_id')}"


SK_LOCAL = "LOCAL"
SK_CATALOGO = "CATALOGO"


# --- operacion -----------------------------------------------------------------------------------

def salon(L: str) -> str:
    return f"{L}#SALON"


def pedido(L: str, pedido_id: str) -> str:
    return f"{L}#PED#{validar_id(pedido_id, 'pedido_id')}"


def sk_item(item_id: str) -> str:
    return f"ITEM#{validar_id(item_id, 'item_id')}"


def sk_pago(pago_id: str) -> str:
    return f"PAGO#{validar_id(pago_id, 'pago_id')}"


SK_PEDIDO = "PEDIDO"


def caja(L: str) -> str:
    return f"{L}#CAJA"


SK_TURNO_ABIERTO = "TURNO_ABIERTO"


def sk_indice_turno(turno_id: str) -> str:
    return f"TURNO#{validar_id(turno_id, 'turno_id')}"


def turno(L: str, turno_id: str) -> str:
    return f"{L}#TURNO#{validar_id(turno_id, 'turno_id')}"


SK_TURNO = "TURNO"


def sk_retiro(retiro_id: str) -> str:
    return f"RETIRO#{validar_id(retiro_id, 'retiro_id')}"


def sk_dte(venta_id: str) -> str:
    return f"DTE#{validar_id(venta_id, 'venta_id')}"


def dia(L: str, fecha: str) -> str:
    return f"{L}#DIA#{fecha}"


def impresora(L: str, impresora_id: str) -> str:
    return f"{L}#IMP#{validar_id(impresora_id, 'impresora_id')}"


def sk_trabajo_pendiente(trabajo_id: str) -> str:
    return f"PEND#{trabajo_id}"


def sk_trabajo_hecho(trabajo_id: str) -> str:
    return f"HECHO#{trabajo_id}"


def retenidos(L: str) -> str:
    return f"{L}#IMPRET"


def sk_retenido(trabajo_id: str) -> str:
    return f"RET#{trabajo_id}"


def conflictos(L: str) -> str:
    return f"{L}#CONFLICTO"


def fallos(L: str) -> str:
    """Registro de mensajes que un consumidor no pudo procesar (diagnóstico, 14 días)."""
    return f"{L}#FALLOS"


def sk_destino(destino_id: str) -> str:
    return f"DESTINO#{validar_id(destino_id, 'destino_id')}"


def autorizaciones(L: str) -> str:
    return f"{L}#AUT"


def sk_bloqueo(sub: str) -> str:
    return f"BLOQUEO#{validar_id(sub, 'sub')}"


def comando(L: str, command_id: str) -> str:
    return f"{L}#CMD#{validar_id(command_id, 'command_id')}"


SK_CMD = "CMD"


def eventos(L: str) -> str:
    return f"{L}#EVT"


def sk_evento(event_id: str) -> str:
    return f"EVT#{event_id}"


def procesados(L: str) -> str:
    return f"{L}#PROC"


def sk_contador_folio(tipo_documento: str) -> str:
    return f"CONTADOR#FOLIO#{tipo_documento}"


SALUD = "SALUD"

# Índice disperso de vigilancia (GSI1 de operacion)
VIGILAR_DTE = "VIGILAR#DTE"
VIGILAR_TURNO = "VIGILAR#TURNO"
VIGILAR_IMPRESION = "VIGILAR#IMPRESION"
