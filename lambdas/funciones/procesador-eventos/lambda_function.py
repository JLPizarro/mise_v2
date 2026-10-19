"""Función `procesador-eventos`: consume DynamoDB Streams de `operacion` (solo ítems EVT#).

Efectos de cada evento, todos idempotentes por event_id:
1. Agregados del turno y del día: ADD + marca L#PROC / AGG#<event_id> en la misma transacción,
   con condición, para que un reintento no cuente dos veces.
2. Archivo histórico JSON.gz en S3 (clave determinista: sobrescribir es inocuo).
3. Comprobante HTML de la venta en S3 (clave determinista).
4. venta.cerrada -> mensaje a dte-emision (emision-dte es idempotente por venta_id).
5. Avisos por SNS: la marca L#PROC / SNS#<event_id> se escribe DESPUÉS de publicar. Puede llegar
   un correo duplicado, pero nunca se pierde uno.

Respuesta de fallos parciales (ReportBatchItemFailures): ante el primer registro que falla se
devuelve su número de secuencia; Lambda reintenta desde ahí y los efectos ya aplicados se omiten.

Disparador: Streams de `operacion`, filtro {"eventName":["INSERT"],"dynamodb":{"Keys":{"SK":{"S":[{"prefix":"EVT#"}]}}}}
Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, BUCKET_ARCHIVO, COLA_DTE_URL, TEMA_DUENO_ARN,
           TEMA_ALERTAS_ARN, LOG_LEVEL (opcional)
"""

import logging
import os

from pos_dominio import claves, efectos, tiempo
from pos_dominio.cambios import Crear, Sumar
from pos_dominio.contexto import Contexto
from pos_dominio.errores import ErrorDominio
from pos_dominio.infra import aws, fallos, logs
from pos_dominio.infra.dynamodb import desde_item

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION", "BUCKET_ARCHIVO", "COLA_DTE_URL", "TEMA_DUENO_ARN",
                   "TEMA_ALERTAS_ARN")
log = logging.getLogger("pos.procesador")
OP = claves.TABLA_OPERACION
TTL_PROC = 8 * 24 * 3600


def _ctx_sistema(evento: dict) -> Contexto:
    return Contexto(tenant_id=evento["tenant_id"], local_id=evento["local_id"], usuario_id="procesador-eventos",
                    rol="sistema", command_id="")


def _marca(evento: dict, efecto: str) -> dict:
    return {"tipo_item": "PROC", "event_id": evento["event_id"], "efecto": efecto,
            "expira_en": tiempo.epoch(tiempo.ahora_utc()) + TTL_PROC}


def aplicar_agregados(evento: dict) -> None:
    sumas = efectos.agregados(evento)
    if not sumas:
        return
    L = claves.local(evento["tenant_id"], evento["local_id"])
    cambios = [Sumar(tabla=OP, pk=pk, sk=sk, incrementos=incrementos) for pk, sk, incrementos in sumas]
    cambios.append(Crear(tabla=OP, pk=claves.procesados(L), sk=f"AGG#{evento['event_id']}",
                         atributos=_marca(evento, "agregados")))
    try:
        aws.almacen().aplicar_sistema(_ctx_sistema(evento), cambios, [])
    except ErrorDominio:
        # La marca ya existía: este evento ya se sumó en un intento anterior.
        log.info("agregados ya aplicados", extra={"event_id": evento["event_id"]})


def aplicar_archivo(evento: dict) -> None:
    aws.subir(os.environ["BUCKET_ARCHIVO"], efectos.clave_archivo(evento), efectos.contenido_archivo(evento),
              tipo="application/json", codificacion="gzip")


def aplicar_venta(evento: dict) -> None:
    if evento["tipo"] != "venta.cerrada":
        return
    aws.subir(os.environ["BUCKET_ARCHIVO"], efectos.clave_comprobante(evento),
              efectos.comprobante_html(evento).encode("utf-8"), tipo="text/html; charset=utf-8")
    aws.encolar(os.environ["COLA_DTE_URL"], efectos.mensaje_dte(evento))


def aplicar_avisos(evento: dict) -> None:
    avisos = efectos.avisos(evento)
    if not avisos:
        return
    L = claves.local(evento["tenant_id"], evento["local_id"])
    almacen = aws.almacen()
    if almacen.obtener(OP, claves.procesados(L), f"SNS#{evento['event_id']}") is not None:
        return
    # El tema y los atributos de cada aviso salen del catálogo central (pos_dominio.mensajeria).
    for aviso_id, asunto, mensaje in avisos:
        aws.publicar_aviso(aviso_id, evento["tenant_id"], evento["local_id"], asunto, mensaje)
    try:
        almacen.aplicar_sistema(_ctx_sistema(evento), [
            Crear(tabla=OP, pk=claves.procesados(L), sk=f"SNS#{evento['event_id']}", atributos=_marca(evento, "sns"))], [])
    except ErrorDominio:
        pass


def procesar(evento: dict) -> None:
    logs.correlacion(event_id=evento["event_id"], tenant_id=evento["tenant_id"], local_id=evento["local_id"])
    aplicar_agregados(evento)
    aplicar_archivo(evento)
    aplicar_venta(evento)
    aplicar_avisos(evento)


def lambda_handler(entrada: dict, _contexto=None) -> dict:
    logs.configurar()
    for registro in entrada.get("Records", []):
        secuencia = registro.get("dynamodb", {}).get("SequenceNumber")
        imagen: dict | None = None
        try:
            imagen = desde_item(registro.get("dynamodb", {}).get("NewImage"))
            # Además del filtro del disparador: cualquier ítem que no sea un evento se descarta.
            if registro.get("eventName") != "INSERT" or not imagen or imagen.get("tipo_item") != "EVT":
                continue
            procesar(imagen)
        except Exception as error:  # noqa: BLE001 - se reporta el registro y se reintenta desde él
            log.exception("falló un evento; se reintentará desde este registro", extra={"secuencia": secuencia})
            imagen = imagen or {}
            fallos.registrar(consumidor="procesador-eventos", canal="eventos", mensaje_id=str(secuencia or ""),
                             intento=1, error=error, tenant_id=imagen.get("tenant_id"), local_id=imagen.get("local_id"),
                             referencia=f"{imagen.get('tipo')} {imagen.get('event_id')}")
            return {"batchItemFailures": [{"itemIdentifier": secuencia}]}
        finally:
            logs.limpiar_correlacion()
    return {"batchItemFailures": []}
