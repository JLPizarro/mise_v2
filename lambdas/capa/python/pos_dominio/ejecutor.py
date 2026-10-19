"""Ejecuta una operación de negocio con idempotencia por X-Command-Id.

Flujo:
1. Verifica el rol (matriz en pos_dominio.roles).
2. Si el comando ya existe (ítem CMD), devuelve su respuesta guardada. Si el ID se reutilizó con
   otro cuerpo u otra operación, responde 422 COMANDO_REUTILIZADO.
3. Lee el estado, decide (puro) y aplica todo en una transacción: CMD + cambios + EVT.
4. Si una condición de versión falló, relee y decide otra vez (una sola vez). Si vuelve a fallar,
   409 CONFLICTO_CONCURRENCIA.
5. Los rechazos de negocio definitivos se guardan en el CMD (M9): el mismo comando siempre
   recibe la misma respuesta.

El almacén es cualquier objeto con los métodos de lectura que piden las operaciones más
`leer_comando`, `aplicar` y `guardar_rechazo` (ver pos_dominio.infra.dynamodb.AlmacenDynamo).
"""

import hashlib
import json
from dataclasses import dataclass

from pos_dominio import roles, validacion
from pos_dominio.cambios import Rechazo
from pos_dominio.errores import ComandoDuplicado, ConflictoConcurrencia, ErrorDominio, Reintentar, Validacion

INTENTOS = 2


@dataclass
class Respuesta:
    http: int
    cuerpo: dict
    repetida: bool = False


def hash_cuerpo(nombre_operacion: str, cuerpo: dict) -> str:
    canonico = json.dumps({"op": nombre_operacion, "cuerpo": cuerpo}, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _repetir(previo: dict, huella: str) -> Respuesta:
    if previo.get("hash_cuerpo") != huella:
        raise Validacion("El X-Command-Id ya se usó para otra operación", codigo="COMANDO_REUTILIZADO")
    return Respuesta(int(previo["http_status"]), json.loads(previo["respuesta"]), repetida=True)


def ejecutar(almacen, operacion, ctx, cuerpo: dict, *, registrar_rechazo: bool = True) -> Respuesta:
    """registrar_rechazo=False: el que llama guarda el rechazo él mismo (drenador-contingencia lo
    guarda junto con el CONFLICTO#, en la misma transacción)."""
    roles.exigir(ctx.rol, operacion.accion)
    validacion.command_id(ctx.command_id)
    huella = hash_cuerpo(operacion.nombre, cuerpo)

    previo = almacen.leer_comando(ctx.L, ctx.command_id)
    if previo is not None:
        return _repetir(previo, huella)

    ultimo_error = None
    for _ in range(INTENTOS):
        try:
            estado = operacion.leer(almacen, ctx, cuerpo)
            resultado = operacion.decidir(estado, ctx, cuerpo)
        except ErrorDominio as error:
            if registrar_rechazo and not error.transitorio:
                almacen.guardar_rechazo(ctx, operacion.nombre, huella, error)
            raise

        if isinstance(resultado, Rechazo):
            try:
                almacen.aplicar(ctx, operacion.nombre, huella, http=resultado.error.http,
                                respuesta=resultado.error.cuerpo(), estado_cmd="rechazado",
                                cambios=resultado.cambios, eventos=resultado.eventos)
            except ComandoDuplicado:
                return _repetir(almacen.leer_comando(ctx.L, ctx.command_id), huella)
            except Reintentar as senal:
                ultimo_error = senal.error
                continue
            raise resultado.error
        if resultado.sin_escritura:
            return Respuesta(resultado.http, resultado.respuesta)
        try:
            almacen.aplicar(ctx, operacion.nombre, huella, http=resultado.http, respuesta=resultado.respuesta,
                            estado_cmd="aplicado", cambios=resultado.cambios, eventos=resultado.eventos)
            return Respuesta(resultado.http, resultado.respuesta)
        except ErrorDominio as error:
            # Condición de negocio que falló al escribir (por ejemplo, el turno se cerró entremedio).
            if registrar_rechazo and not error.transitorio:
                almacen.guardar_rechazo(ctx, operacion.nombre, huella, error)
            raise
        except ComandoDuplicado:
            return _repetir(almacen.leer_comando(ctx.L, ctx.command_id), huella)
        except Reintentar as senal:
            ultimo_error = senal.error

    if ultimo_error is not None and not ultimo_error.transitorio:
        raise ultimo_error
    raise ConflictoConcurrencia("Otra operación cambió estos datos al mismo tiempo. Intenta de nuevo.")
