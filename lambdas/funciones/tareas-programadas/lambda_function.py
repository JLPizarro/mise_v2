"""Función `tareas-programadas`: la invoca una regla de EventBridge cada 5 minutos.

Vigila lo que quedó atascado, usando el índice disperso GSI1 de `operacion` (solo contiene lo
vigilable; no recorre la tabla):
1. Documentos tributarios en `pendiente` o `enviando` hace más de 15 minutos: los vuelve a encolar
   en dte-emision (emision-dte es idempotente).
2. Turnos de caja abiertos hace más de 18 horas: avisa al dueño una vez.
3. Trabajos de impresión pendientes hace más de 10 minutos (impresora apagada o sin red): avisa al
   equipo técnico una vez.

No toma decisiones de negocio: solo reintenta y avisa. Son mecanismos de operación, no reglas del
POS; los umbrales se ajustan con variables de entorno.

Disparador: regla de EventBridge `rate(5 minutes)` (no EventBridge Scheduler, que exige un rol propio).
Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, COLA_DTE_URL, TEMA_DUENO_ARN, TEMA_ALERTAS_ARN,
           MINUTOS_DTE (15), HORAS_TURNO (18), MINUTOS_IMPRESION (10), LOG_LEVEL (opcional)
"""

import logging
import os
from datetime import timedelta

from pos_dominio import claves, tiempo
from pos_dominio.errores import ErrorDominio
from pos_dominio.infra import aws, logs

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION", "COLA_DTE_URL", "TEMA_DUENO_ARN", "TEMA_ALERTAS_ARN")
log = logging.getLogger("pos.tareas")
OP = claves.TABLA_OPERACION


def _partes(pk: str) -> tuple[str, str]:
    partes = pk.split("#")
    return partes[1], partes[3]


def _marcar_avisado(item: dict) -> bool:
    """True si esta ejecución es la primera en avisar (marca con condición)."""
    try:
        aws.almacen().actualizar(OP, item["PK"], item["SK"], asignar={"avisado_en": tiempo.iso(tiempo.ahora_utc())},
                                 condicion=("y", (("existe", "PK"), ("no_existe", "avisado_en"))))
        return True
    except ErrorDominio:
        return False


def revisar_dte(ahora) -> int:
    limite = tiempo.iso(ahora - timedelta(minutes=int(os.environ.get("MINUTOS_DTE", "15"))))
    n = 0
    for item in aws.almacen().vigilados(claves.VIGILAR_DTE, limite):
        tenant_id, local_id = _partes(item["PK"])
        aws.encolar(os.environ["COLA_DTE_URL"], {"tenant_id": tenant_id, "local_id": local_id,
                                                 "turno_id": item["turno_id"], "venta_id": item["venta_id"]})
        n += 1
    return n


def revisar_turnos(ahora) -> int:
    limite = tiempo.iso(ahora - timedelta(hours=int(os.environ.get("HORAS_TURNO", "18"))))
    n = 0
    for item in aws.almacen().vigilados(claves.VIGILAR_TURNO, limite):
        if item.get("avisado_en") or not _marcar_avisado(item):
            continue
        tenant_id, local_id = _partes(item["PK"])
        aws.publicar_aviso("turno_abierto_demasiado", tenant_id, local_id,
                           "MISE: turno de caja abierto hace demasiado tiempo",
                           f"Local {local_id} ({tenant_id}): el turno {item['turno_id']} está abierto desde "
                           f"{item['abierto_en']}. Revisa si falta cerrarlo.")
        n += 1
    return n


def revisar_impresion(ahora) -> int:
    limite = tiempo.iso(ahora - timedelta(minutes=int(os.environ.get("MINUTOS_IMPRESION", "10"))))
    n = 0
    for item in aws.almacen().vigilados(claves.VIGILAR_IMPRESION, limite):
        if item.get("avisado_en") or not _marcar_avisado(item):
            continue
        tenant_id, local_id = _partes(item["PK"])
        aws.publicar_aviso("impresora_sin_retirar", tenant_id, local_id, "MISE: impresora sin retirar trabajos",
                           f"Local {local_id} ({tenant_id}): la impresora {item.get('impresora_id')} tiene un trabajo "
                           f"pendiente desde {item.get('creado_en')} (tipo {item.get('tipo')}).")
        n += 1
    return n


def lambda_handler(_evento=None, _contexto=None) -> dict:
    logs.configurar()
    ahora = tiempo.ahora_utc()
    resultado = {}
    for nombre, tarea in (("dte_reencolados", revisar_dte), ("turnos_avisados", revisar_turnos),
                          ("impresiones_avisadas", revisar_impresion)):
        try:
            resultado[nombre] = tarea(ahora)
        except Exception:  # noqa: BLE001 - una tarea que falla no detiene a las demás
            log.exception("falló una tarea programada", extra={"tarea": nombre})
            resultado[nombre] = "error"
    if any(v == "error" for v in resultado.values()):
        log.error("tareas programadas con errores", extra=resultado)
    return resultado
