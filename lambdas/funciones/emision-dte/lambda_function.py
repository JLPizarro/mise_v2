"""Función `emision-dte`: consume la cola estándar dte-emision y emite el documento tributario (simulado).

Por mensaje ({tenant_id, local_id, turno_id, venta_id}):
1. Lee DTE#venta_id. Si ya está emitido o rechazado: nada que hacer (idempotente). Un `fallido`
   que vuelve por reenvío desde la cola de fallidos se intenta de nuevo.
2. Lo marca `enviando` y suma un intento.
3. Asigna folio con el contador atómico del cliente y tipo (si no tenía).
4. Llama al proveedor (EmisorDTE). Resultados:
   - emitido: guarda folio y timbre, crea el trabajo de impresión en la impresora de caja (clave
     determinista: nunca se imprime dos veces) y escribe dte.emitido.
   - rechazado: no se reintenta; escribe dte.rechazado (aviso al dueño).
   - 429 / 5xx / tiempo agotado: se reintenta con espera creciente (cambia la visibilidad del
     mensaje). En la última recepción permitida marca `fallido`; SQS lo mueve a dte-emision-fallidos.

Disparador: SQS dte-emision, lote pequeño, respuesta de fallos parciales activada, concurrencia
máxima fija (límite del proveedor).
Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, COLA_DTE_URL, MAX_RECEPCIONES (= la de la cola, 5),
           DTE_MODO, DTE_TASA_FALLA, DTE_LATENCIA_MS, LOG_LEVEL (opcional)
"""

import json
import logging
import os

from pos_dominio import claves, dte, tiempo
from pos_dominio.cambios import Crear, Evento, Guardar
from pos_dominio.contexto import Contexto
from pos_dominio.errores import ErrorDominio
from pos_dominio.infra import aws, fallos, logs
from pos_dominio.operaciones.caja import trabajo_documento

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION", "COLA_DTE_URL")
log = logging.getLogger("pos.dte")
OP = claves.TABLA_OPERACION
# `fallido` no es final: si el mensaje vuelve (reenvío desde la cola de fallidos tras arreglar el
# proveedor), se intenta de nuevo con el mismo folio.
FINALES = ("emitido", "rechazado")


def _emisor():
    return dte.EmisorSimulado.desde_entorno(os.environ)


def _guardar_dte(L: str, turno_id: str, actual: dict, cambios: dict, quitar_vigilancia: bool) -> Guardar:
    atributos = {k: v for k, v in actual.items() if k not in ("PK", "SK", "version")}
    atributos.update(cambios)
    if quitar_vigilancia:
        atributos.pop("GSI1PK", None)
        atributos.pop("GSI1SK", None)
    return Guardar(tabla=OP, pk=claves.turno(L, turno_id), sk=claves.sk_dte(actual["venta_id"]),
                   atributos={k: v for k, v in atributos.items() if v is not None},
                   version_leida=actual.get("version", 1), reintentar=False)


def _folio(almacen, tenant_id: str, L: str, documento: dict) -> int:
    if documento.get("folio"):
        return int(documento["folio"])
    contador = almacen.actualizar(OP, claves.tenant(tenant_id), claves.sk_contador_folio(documento["tipo"]),
                                  sumar={"ultimo": 1}, devolver=True)
    folio = int(contador["ultimo"])
    try:
        almacen.actualizar(OP, claves.turno(L, documento["turno_id"]), claves.sk_dte(documento["venta_id"]),
                           asignar={"folio": folio}, condicion=("no_existe", "folio"))
    except ErrorDominio:
        # Otro intento asignó folio primero: se usa el suyo y este número queda como hueco (documentado).
        folio = int(almacen.obtener(OP, claves.turno(L, documento["turno_id"]), claves.sk_dte(documento["venta_id"]))["folio"])
    return folio


def procesar(mensaje: dict, recepcion: int, max_recepciones: int, emisor, mensaje_id: str = "") -> bool:
    """Devuelve True si el mensaje terminó (se borra de la cola) y False si debe reintentarse."""
    almacen = aws.almacen()
    tenant_id, local_id = mensaje["tenant_id"], mensaje["local_id"]
    L = claves.local(tenant_id, local_id)
    logs.correlacion(tenant_id=tenant_id, local_id=local_id, venta_id=mensaje["venta_id"])
    pk, sk = claves.turno(L, mensaje["turno_id"]), claves.sk_dte(mensaje["venta_id"])
    actual = almacen.obtener(OP, pk, sk)
    if actual is None:
        log.error("no existe el documento a emitir")
        return True
    if actual["estado"] in FINALES:
        return True

    # GSI1SK = hora de este intento: tareas-programadas solo reencola si pasan 15 min sin intentos.
    marca = f"{tiempo.iso(tiempo.ahora_utc())}#{mensaje['venta_id']}"
    actual = almacen.actualizar(OP, pk, sk, asignar={"estado": "enviando", "GSI1PK": claves.VIGILAR_DTE, "GSI1SK": marca},
                                sumar={"intentos": 1, "version": 1},
                                condicion=("in", "estado", ("pendiente", "enviando", "fallido")), devolver=True)
    folio = _folio(almacen, tenant_id, L, actual)
    actual = almacen.obtener(OP, pk, sk)
    ctx = Contexto(tenant_id=tenant_id, local_id=local_id, usuario_id="emision-dte", rol="sistema", command_id="")
    ahora = tiempo.iso(tiempo.ahora_utc())

    try:
        resultado = emisor.emitir(actual, folio)
    except dte.ErrorProveedor as error:
        log.warning("falla transitoria del proveedor", extra={"tipo_falla": error.tipo, "recepcion": recepcion})
        fallos.registrar(consumidor="emision-dte", canal="dte-emision", mensaje_id=mensaje_id, intento=recepcion,
                         error=error, mensaje=f"Proveedor no disponible ({error.tipo})", tenant_id=tenant_id, local_id=local_id,
                         referencia=f"venta {mensaje['venta_id']}", recuperable=recepcion < max_recepciones)
        if recepcion >= max_recepciones:
            almacen.aplicar_sistema(ctx, [_guardar_dte(L, mensaje["turno_id"], actual, {
                "estado": "fallido", "motivo_rechazo": f"Proveedor no disponible ({error.tipo})", "fallido_en": ahora},
                quitar_vigilancia=True)],
                [Evento("dte.fallido", {"venta_id": actual["venta_id"], "turno_id": mensaje["turno_id"],
                                        "tipo_falla": error.tipo})])
        return False

    if not resultado.aceptado:
        almacen.aplicar_sistema(ctx, [_guardar_dte(L, mensaje["turno_id"], actual, {
            "estado": "rechazado", "motivo_rechazo": resultado.motivo, "rechazado_en": ahora}, quitar_vigilancia=True)],
            [Evento("dte.rechazado", {"venta_id": actual["venta_id"], "folio": folio, "motivo": resultado.motivo})])
        return True

    emitido = {"estado": "emitido", "folio": folio, "timbre": resultado.timbre, "emitido_en": ahora}
    cambios = [_guardar_dte(L, mensaje["turno_id"], actual, emitido, quitar_vigilancia=True)]
    config = almacen.config_local(L)
    impresora_id = config.impresora_caja_id if config else None
    if impresora_id:
        trabajo = trabajo_documento({**actual, **emitido}, impresora_id, f"DTE-{actual['venta_id']}", ahora)
        cambios.append(Crear(tabla=OP, pk=claves.impresora(L, impresora_id),
                             sk=claves.sk_trabajo_pendiente(trabajo["trabajo_id"]), atributos=trabajo))
    else:
        log.warning("el local no tiene impresora de caja: el documento no se imprime")
    almacen.aplicar_sistema(ctx, cambios, [Evento("dte.emitido", {"venta_id": actual["venta_id"], "folio": folio,
                                                                  "tipo": actual["tipo"]})])
    return True


def lambda_handler(entrada: dict, _contexto=None) -> dict:
    logs.configurar()
    emisor = _emisor()
    max_recepciones = int(os.environ.get("MAX_RECEPCIONES", "5"))
    fallidos = []
    for registro in entrada.get("Records", []):
        recepcion = int(registro.get("attributes", {}).get("ApproximateReceiveCount", "1"))
        mensaje: dict = {}
        try:
            mensaje = json.loads(registro["body"])
            terminado = procesar(mensaje, recepcion, max_recepciones, emisor, registro["messageId"])
        except Exception as error:  # noqa: BLE001 - se reintenta solo este mensaje
            log.exception("error al emitir el documento")
            fallos.registrar(consumidor="emision-dte", canal="dte-emision", mensaje_id=registro["messageId"],
                             intento=recepcion, error=error, tenant_id=mensaje.get("tenant_id"),
                             local_id=mensaje.get("local_id"), referencia=f"venta {mensaje.get('venta_id')}",
                             recuperable=recepcion < max_recepciones)
            terminado = False
        if not terminado:
            fallidos.append({"itemIdentifier": registro["messageId"]})
            if recepcion < max_recepciones:
                try:
                    aws.cambiar_visibilidad(os.environ["COLA_DTE_URL"], registro["receiptHandle"],
                                            dte.espera_reintento(recepcion))
                except Exception:  # noqa: BLE001 - sin backoff igual se reintenta con la visibilidad de la cola
                    log.warning("no se pudo ajustar la visibilidad del mensaje")
        logs.limpiar_correlacion()
    return {"batchItemFailures": fallidos}
