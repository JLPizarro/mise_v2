"""Función `pedidos`: comanda de la mesa.

Si DynamoDB falla por infraestructura (no por un rechazo de negocio), el comando completo se
encola en contingencia-comandas.fifo y se responde 202 {"estado": "aceptada_en_contingencia"}.
drenador-contingencia lo reaplica después con los mismos casos de uso del dominio.

Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, COLA_CONTINGENCIA_URL, LOG_LEVEL (opcional),
           SIMULAR_FALLA_DYNAMODB (solo para el simulacro; nunca en uso normal)
"""

import logging
import os

from pos_dominio import tiempo
from pos_dominio.errores import ErrorInfraestructura
from pos_dominio.infra import api, aws, http
from pos_dominio.operaciones import pedidos as P

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION", "COLA_CONTINGENCIA_URL")
app = http.Aplicacion("pedidos")
log = logging.getLogger("pos.pedidos")


def mensaje_contingencia(peticion: http.Peticion, operacion, cuerpo: dict, entrada: str) -> dict:
    claims = peticion.claims
    local_id = peticion.parametros.get("local_id") or cuerpo.get("local_id")
    grupo = cuerpo.get("mesa_id") or cuerpo.get("pedido_id") or "sin_mesa"
    return {
        "v": 1, "operacion": operacion.nombre, "local_id": local_id, "grupo": f"{local_id}#{grupo}",
        "cuerpo": cuerpo, "command_id": peticion.command_id, "sub": claims.get("sub"),
        "email": claims.get("email", ""), "nombre": claims.get("name", ""),
        "ocurrido_en": tiempo.iso(tiempo.ahora_utc()), "entrada": entrada, "request_id": peticion.request_id,
    }


def encolar_contingencia(mensaje: dict) -> None:
    # MessageGroupId = local#mesa conserva el orden por mesa. La deduplicación de SQS dura 5 min;
    # la definitiva la da el ítem CMD# al reaplicar.
    aws.encolar(os.environ["COLA_CONTINGENCIA_URL"], mensaje, grupo=mensaje["grupo"],
                deduplicacion=mensaje["command_id"])


def _escribir(peticion: http.Peticion, operacion, cuerpo: dict):
    try:
        return api.ejecutar_http(peticion, operacion, cuerpo)
    except ErrorInfraestructura as error:
        log.error("falla de infraestructura: comando a contingencia", extra={"causa": error.causa})
        encolar_contingencia(mensaje_contingencia(peticion, operacion, cuerpo, "servidor"))
        return http.respuesta(202, {"estado": "aceptada_en_contingencia", "command_id": peticion.command_id})


def _cuerpo(peticion):
    return peticion.cuerpo_con_ruta("local_id")


@app.ruta("POST /locales/{local_id}/pedidos", escritura=True)
def abrir(peticion):
    return _escribir(peticion, P.ABRIR, _cuerpo(peticion))


@app.ruta("GET /locales/{local_id}/pedidos/{pedido_id}")
def ver(peticion):
    ctx = api.contexto(peticion, accion="salon.ver")
    return 200, P.ver_pedido(P.leer_pedido(aws.almacen(), ctx, {"pedido_id": peticion.parametros["pedido_id"]}))


@app.ruta("POST /locales/{local_id}/pedidos/{pedido_id}/items", escritura=True)
def agregar(peticion):
    return _escribir(peticion, P.AGREGAR_ITEM, _cuerpo(peticion))


@app.ruta("PATCH /locales/{local_id}/pedidos/{pedido_id}/items/{item_id}", escritura=True)
def modificar(peticion):
    return _escribir(peticion, P.MODIFICAR_ITEM, _cuerpo(peticion))


@app.ruta("DELETE /locales/{local_id}/pedidos/{pedido_id}/items/{item_id}", escritura=True)
def quitar(peticion):
    return _escribir(peticion, P.QUITAR_ITEM, _cuerpo(peticion))


@app.ruta("POST /locales/{local_id}/pedidos/{pedido_id}/enviar", escritura=True)
def enviar(peticion):
    return _escribir(peticion, P.ENVIAR_TANDA, _cuerpo(peticion))


@app.ruta("POST /locales/{local_id}/pedidos/{pedido_id}/precuenta", escritura=True)
def precuenta(peticion):
    return _escribir(peticion, P.PRECUENTA, _cuerpo(peticion))


@app.ruta("POST /locales/{local_id}/pedidos/{pedido_id}/reabrir", escritura=True)
def reabrir(peticion):
    return _escribir(peticion, P.REABRIR, _cuerpo(peticion))


lambda_handler = app
