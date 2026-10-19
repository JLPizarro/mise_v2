"""Función `reportes`: turnos, reporte de un turno y resumen del día.

Los agregados (AGG#) los escribe `procesador-eventos` y llegan con unos segundos de retraso. Los
totales de caja del turno (efectivo, débito, crédito, transferencia, retiros) son síncronos y
exactos: se escriben en la misma transacción de cada pago o retiro.

Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, LOG_LEVEL (opcional)
"""

import re

from pos_dominio import claves
from pos_dominio.errores import NoEncontrado, Validacion
from pos_dominio.infra import api, aws, http
from pos_dominio.modelos import Turno

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION")
app = http.Aplicacion("reportes")
OP = claves.TABLA_OPERACION
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fecha(valor, campo: str) -> str | None:
    if valor is None:
        return None
    if not _FECHA.match(valor):
        raise Validacion(f"{campo} debe tener el formato AAAA-MM-DD", codigo="CAMPO_INVALIDO", detalle={"campo": campo})
    return valor


def _sin_claves(fila: dict) -> dict:
    return {k: v for k, v in fila.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK", "tipo_item")}


@app.ruta("GET /locales/{local_id}/reportes/turnos")
def turnos(peticion):
    ctx = api.contexto(peticion, accion="reportes.ver")
    desde = _fecha(peticion.query.get("desde"), "desde")
    hasta = _fecha(peticion.query.get("hasta"), "hasta")
    filas = aws.almacen().listar(OP, claves.caja(ctx.L), "TURNO#")
    filas = [f for f in filas if (not desde or f["fecha_operativa"] >= desde) and (not hasta or f["fecha_operativa"] <= hasta)]
    return 200, {"turnos": [_sin_claves(f) for f in sorted(filas, key=lambda f: f["SK"], reverse=True)[:400]]}


@app.ruta("GET /locales/{local_id}/reportes/turnos/{turno_id}")
def reporte_turno(peticion):
    ctx = api.contexto(peticion, accion="reportes.ver")
    turno_id = claves.validar_id(peticion.parametros["turno_id"], "turno_id")
    filas = aws.almacen().listar(OP, claves.turno(ctx.L, turno_id), consistente=True)
    cabecera = next((f for f in filas if f["SK"] == claves.SK_TURNO), None)
    if cabecera is None:
        raise NoEncontrado("Turno no encontrado", codigo="TURNO_NO_ENCONTRADO")
    turno = Turno.desde_atributos(cabecera)
    resumen = next((f for f in filas if f["SK"] == "AGG#RESUMEN"), {})
    documentos = [f for f in filas if f["SK"].startswith("DTE#")]
    por_estado: dict[str, int] = {}
    for documento in documentos:
        por_estado[documento["estado"]] = por_estado.get(documento["estado"], 0) + 1
    return 200, {
        "turno": {**_sin_claves(cabecera), "efectivo_esperado": turno.efectivo_esperado},
        "caja": {"efectivo": turno.tot_efectivo, "debito": turno.tot_debito, "credito": turno.tot_credito,
                 "transferencia": turno.tot_transferencia, "retiros": turno.tot_retiros, "n_pagos": turno.n_pagos,
                 "n_ventas": turno.n_ventas, "total_ventas": turno.tot_ventas},
        "resumen": _sin_claves(resumen),
        "por_garzon": [{"garzon_id": f["SK"].split("#", 2)[2], **_sin_claves(f)}
                       for f in filas if f["SK"].startswith("AGG#GARZON#")],
        "retiros": [_sin_claves(f) for f in filas if f["SK"].startswith("RETIRO#")],
        "documentos": por_estado,
    }


@app.ruta("GET /locales/{local_id}/reportes/dias/{fecha}")
def dia(peticion):
    ctx = api.contexto(peticion, accion="reportes.ver")
    fecha = _fecha(peticion.parametros["fecha"], "fecha")
    resumen = aws.almacen().obtener(OP, claves.dia(ctx.L, fecha), "AGG#RESUMEN", consistente=False)
    return 200, {"fecha": fecha, "resumen": _sin_claves(resumen or {})}


lambda_handler = app
