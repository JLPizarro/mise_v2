"""Función `drenador-contingencia`: consume contingencia-comandas.fifo y reaplica cada comando con los
mismos casos de uso del dominio, marcados con origen = contingencia.

- Idempotente por CMD#: un comando que ya se aplicó (por la ruta normal o en un intento anterior)
  devuelve su respuesta guardada y no escribe de nuevo.
- Rechazo de negocio al reaplicar (por ejemplo, la mesa ya se cerró, o la persona perdió el acceso):
  no se reintenta. Se guarda CONFLICTO# junto con el CMD rechazado y el evento conflicto.registrado,
  en una sola transacción; el procesador de eventos avisa al dueño por SNS.
- Falla de infraestructura (DynamoDB sigue caído): se devuelve como fallo parcial y SQS lo
  reintenta. Con la visibilidad y el número de recepciones de la cola hay unos 90 minutos de
  reintentos antes de mandarlo a la cola de fallidos.
- FIFO: si un mensaje falla, los siguientes del lote también se devuelven, para no romper el orden
  dentro de cada mesa.
- Los trabajos de impresión de estos comandos quedan `retenido_contingencia`: la caja decide si
  imprimirlos, porque probablemente ya se atendieron en papel.

Disparador: SQS contingencia-comandas.fifo, respuesta de fallos parciales activada.
Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, LOG_LEVEL (opcional)
"""

import json
import logging

from pos_dominio import claves, ids, tiempo
from pos_dominio.cambios import Crear, Evento
from pos_dominio.contexto import Contexto
from pos_dominio.ejecutor import ejecutar, hash_cuerpo
from pos_dominio.errores import ComandoDuplicado, ErrorDominio, ErrorInfraestructura
from pos_dominio.infra import aws, fallos, identidad, logs
from pos_dominio.operaciones.pedidos import CONTINGENCIA

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION")
log = logging.getLogger("pos.drenador")
OP = claves.TABLA_OPERACION


def _contexto(mensaje: dict) -> Contexto:
    """Autoriza con la membresía ACTUAL de la persona en `configuracion` (no con lo que diga el mensaje)."""
    sesion = identidad.sesion_de(mensaje["sub"], mensaje.get("email", ""), mensaje.get("nombre", ""), aws.almacen())
    return sesion.contexto(mensaje["local_id"], command_id=mensaje["command_id"], origen="contingencia",
                           request_id=mensaje.get("request_id", ""), ahora=tiempo.desde_iso(mensaje["ocurrido_en"]))


def _registrar_conflicto(mensaje: dict, error: ErrorDominio, ctx: Contexto | None) -> None:
    if ctx is None:
        # Sin membresía no hay cliente desde el cual registrar: se arma el contexto del local con
        # la membresía que haya tenido (aunque esté archivada) o se abandona con un log de error.
        perfil, membresias = aws.almacen().identidad(mensaje["sub"])
        candidata = next((m for m in membresias if m.local_id == mensaje["local_id"]), None)
        if candidata is None:
            log.error("comando de contingencia sin local identificable; se descarta",
                      extra={"command_id": mensaje["command_id"], "error_codigo": error.codigo})
            return
        ctx = Contexto(tenant_id=candidata.tenant_id, local_id=candidata.local_id, usuario_id=mensaje["sub"],
                       rol=candidata.rol, command_id=mensaje["command_id"], origen="contingencia")
    conflicto_id = ids.nuevo_ulid()
    conflicto = {"tipo_item": "CONFLICTO", "conflicto_id": conflicto_id, "estado": "abierto",
                 "motivo": error.mensaje, "codigo_rechazo": error.codigo, "operacion": mensaje["operacion"],
                 "comando": mensaje, "creado_en": tiempo.iso(tiempo.ahora_utc()), "version": 1}
    try:
        aws.almacen().aplicar(ctx, mensaje["operacion"], hash_cuerpo(mensaje["operacion"], mensaje["cuerpo"]),
                              http=error.http, respuesta=error.cuerpo(), estado_cmd="rechazado",
                              cambios=[Crear(tabla=OP, pk=claves.conflictos(ctx.L), sk=f"CONFLICTO#{conflicto_id}",
                                             atributos=conflicto)],
                              eventos=[Evento("conflicto.registrado", {
                                  "conflicto_id": conflicto_id, "operacion": mensaje["operacion"],
                                  "command_id": mensaje["command_id"], "motivo": error.mensaje,
                                  "codigo_rechazo": error.codigo, "mesa": mensaje.get("grupo")})])
    except ComandoDuplicado:
        pass  # el rechazo ya estaba registrado


def procesar(mensaje: dict) -> None:
    logs.correlacion(command_id=mensaje.get("command_id"), local_id=mensaje.get("local_id"))
    operacion = CONTINGENCIA.get(mensaje.get("operacion"))
    if operacion is None:
        log.error("operación no admitida en contingencia; se descarta", extra={"operacion": mensaje.get("operacion")})
        return
    ctx = None
    try:
        ctx = _contexto(mensaje)
        logs.correlacion(tenant_id=ctx.tenant_id)
        respuesta = ejecutar(aws.almacen(), operacion, ctx, mensaje["cuerpo"], registrar_rechazo=False)
        if respuesta.http >= 400:
            log.info("comando ya rechazado antes", extra={"http": respuesta.http})
    except ErrorDominio as error:
        if error.transitorio:
            raise ErrorInfraestructura("conflicto de concurrencia persistente", causa="concurrencia") from error
        log.warning("conflicto al reaplicar", extra={"error_codigo": error.codigo})
        _registrar_conflicto(mensaje, error, ctx)


def _tenant_de(mensaje: dict) -> str | None:
    """Cliente del local del mensaje, según la membresía de quien lo envió (para el registro de fallos)."""
    try:
        _, membresias = aws.almacen().identidad(mensaje["sub"])
        return next((m.tenant_id for m in membresias if m.local_id == mensaje.get("local_id")), None)
    except Exception:  # noqa: BLE001 - si DynamoDB no responde, el fallo queda solo en el log
        return None


def lambda_handler(entrada: dict, _contexto=None) -> dict:
    logs.configurar()
    fallidos = []
    for registro in entrada.get("Records", []):
        if fallidos:
            # FIFO: tras un fallo, el resto del lote se devuelve sin procesar para conservar el orden.
            fallidos.append({"itemIdentifier": registro["messageId"]})
            continue
        mensaje: dict = {}
        try:
            mensaje = json.loads(registro["body"])
            procesar(mensaje)
        except Exception as error:  # noqa: BLE001 - infraestructura u otro error: se reintenta
            log.exception("no se pudo reaplicar el comando; se reintentará")
            fallidos.append({"itemIdentifier": registro["messageId"]})
            recepcion = int(registro.get("attributes", {}).get("ApproximateReceiveCount", "1"))
            fallos.registrar(consumidor="drenador-contingencia", canal="contingencia-comandas",
                             mensaje_id=registro["messageId"], intento=recepcion, error=error,
                             tenant_id=_tenant_de(mensaje), local_id=mensaje.get("local_id"),
                             referencia=f"{mensaje.get('operacion')} {mensaje.get('command_id')}")
        finally:
            logs.limpiar_correlacion()
    return {"batchItemFailures": fallidos}
