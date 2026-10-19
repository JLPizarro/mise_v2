"""Puente entre una petición HTTP y una operación del dominio."""

from pos_dominio import roles
from pos_dominio.ejecutor import ejecutar
from pos_dominio.infra import aws, http, identidad
from pos_dominio.infra.logs import correlacion


def sesion(peticion: http.Peticion) -> identidad.Sesion:
    return identidad.sesion_desde_claims(peticion.claims, aws.almacen())


def contexto(peticion: http.Peticion, *, accion: str | None = None, origen: str = "normal"):
    ctx = sesion(peticion).contexto(peticion.parametros.get("local_id", ""), command_id=peticion.command_id,
                                    request_id=peticion.request_id, origen=origen)
    correlacion(tenant_id=ctx.tenant_id, local_id=ctx.local_id)
    if accion:
        roles.exigir(ctx.rol, accion)
    return ctx


def ejecutar_http(peticion: http.Peticion, operacion, cuerpo: dict, ctx=None):
    ctx = ctx or contexto(peticion)
    resultado = ejecutar(aws.almacen(), operacion, ctx, cuerpo)
    encabezados = {"x-comando-repetido": "true"} if resultado.repetida else {}
    if resultado.http >= 400:
        # Repetición de un comando que ya había sido rechazado: misma respuesta, requestId nuevo.
        cuerpo_error = {**resultado.cuerpo, "requestId": peticion.request_id}
        return http.respuesta(resultado.http, cuerpo_error, encabezados=encabezados)
    return http.respuesta(resultado.http, resultado.cuerpo, encabezados=encabezados)
