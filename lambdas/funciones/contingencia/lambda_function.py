"""Función `contingencia`: recibe comandas cuando la ruta normal falla (5xx, 429 o tiempo agotado tras
un reintento) y las encola en contingencia-comandas.fifo.

A propósito NO toca DynamoDB ni comparte el camino de `pedidos`: si DynamoDB o `pedidos` están
caídos, esta función sigue funcionando. Tiene concurrencia reservada. drenador-contingencia
autoriza y reaplica cada comando cuando el servicio vuelve.

Nunca se usa ante un rechazo de negocio (4xx distinto de 429): eso lo decide la PWA.

Manejador: lambda_function.lambda_handler
Variables: COLA_CONTINGENCIA_URL, LOG_LEVEL (opcional)
"""

import os
from datetime import timedelta

from pos_dominio import claves, tiempo, validacion as v
from pos_dominio.errores import Prohibido, Validacion
from pos_dominio.infra import aws, http
from pos_dominio.operaciones.pedidos import CONTINGENCIA

aws.exigir_entorno("COLA_CONTINGENCIA_URL")
app = http.Aplicacion("contingencia")
TOLERANCIA_RELOJ = timedelta(hours=24)


@app.ruta("POST /contingencia/comandas", escritura=True)
def recibir(peticion):
    claims = peticion.claims
    if not claims.get("sub"):
        raise Prohibido("Falta la identidad del usuario", codigo="SIN_IDENTIDAD")
    if str(claims.get("email_verified")).lower() != "true":
        raise Prohibido("El email de la cuenta de Google no está verificado", codigo="EMAIL_NO_VERIFICADO")

    datos = peticion.json()
    operacion = v.uno_de(datos, "operacion", set(CONTINGENCIA))
    local_id = claves.validar_id(v.texto(datos, "local_id", max_largo=64), "local_id")
    cuerpo = v.objeto(datos.get("cuerpo"), "cuerpo")
    grupo = cuerpo.get("mesa_id") or cuerpo.get("pedido_id")
    if not grupo:
        raise Validacion("El comando debe indicar mesa_id o pedido_id", codigo="SIN_MESA")
    claves.validar_id(grupo, "mesa_id")

    ahora = tiempo.ahora_utc()
    ocurrido = ahora
    if isinstance(datos.get("ocurrido_en"), str):
        try:
            propuesto = tiempo.desde_iso(datos["ocurrido_en"])
            if abs(propuesto - ahora) <= TOLERANCIA_RELOJ:
                ocurrido = propuesto
        except ValueError:
            pass

    mensaje = {
        "v": 1, "operacion": operacion, "local_id": local_id, "grupo": f"{local_id}#{grupo}", "cuerpo": cuerpo,
        "command_id": peticion.command_id, "sub": claims["sub"], "email": claims.get("email", ""),
        "nombre": claims.get("name", ""), "ocurrido_en": tiempo.iso(ocurrido), "entrada": "cliente",
        "request_id": peticion.request_id,
    }
    aws.encolar(os.environ["COLA_CONTINGENCIA_URL"], mensaje, grupo=mensaje["grupo"],
                deduplicacion=peticion.command_id)
    return 202, {"estado": "aceptada_en_contingencia", "command_id": peticion.command_id}


lambda_handler = app
