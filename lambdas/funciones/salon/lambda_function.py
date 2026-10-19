"""Función `salon`: salud del servicio, identidad, plano de mesas, carta y gestión de mesas.

Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, LOG_LEVEL (opcional)
"""

import os

from pos_dominio import claves, roles
from pos_dominio.infra import api, aws, http
from pos_dominio.operaciones import salon

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION")
app = http.Aplicacion("salon")
CFG, OP = claves.TABLA_CONFIGURACION, claves.TABLA_OPERACION


@app.ruta("GET /salud", publica=True)
def salud(peticion):
    """Sin autenticación. La PWA la consulta para saber cuándo vaciar su cola local: responde 200 solo
    si DynamoDB responde; si no, 503."""
    return 200, {"estado": "ok", **aws.almacen().salud(), "version": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "")}


@app.ruta("GET /yo")
def yo(peticion):
    sesion = api.sesion(peticion)
    almacen = aws.almacen()
    locales = []
    for membresia in sesion.membresias:
        if not membresia.activa:
            continue
        L = claves.local(membresia.tenant_id, membresia.local_id)
        local = almacen.config_local(L)
        estaciones = almacen.listar(CFG, L, "ESTACION#") if roles.permitido(membresia.rol, "caja.cobrar") else []
        locales.append({
            "tenant_id": membresia.tenant_id, "local_id": membresia.local_id, "rol": membresia.rol,
            "nombre_local": local.nombre_local if local else membresia.local_id, "marca": local.marca if local else "",
            "propina_sugerida_pct": local.propina_sugerida_pct if local else 10,
            "estaciones_caja": [e["estacion_id"] for e in estaciones],
            "puede_autorizar": roles.permitido(membresia.rol, "autorizar") and bool(membresia.pin_hash),
        })
    return 200, {"sub": sesion.sub, "email": sesion.email, "nombre": sesion.nombre, "locales": locales}


@app.ruta("GET /locales/{local_id}/salon")
def plano(peticion):
    ctx = api.contexto(peticion, accion="salon.ver")
    almacen = aws.almacen()
    solo_estado = peticion.query.get("solo_estado") in ("1", "true")
    estructuras = almacen.listar(CFG, ctx.L, salon.PREFIJO_MESA)
    sectores = [] if solo_estado else almacen.listar(CFG, ctx.L, salon.PREFIJO_SECTOR)
    estados = almacen.listar(OP, claves.salon(ctx.L), salon.PREFIJO_MESA)
    return 200, salon.plano(estructuras, sectores, estados, solo_estado=solo_estado)


@app.ruta("GET /locales/{local_id}/catalogo")
def carta(peticion):
    ctx = api.contexto(peticion, accion="salon.ver")
    almacen = aws.almacen()
    version = (almacen.obtener(CFG, ctx.L, salon.SK_CATALOGO, consistente=False) or {}).get("version", 0)
    if peticion.query.get("version") == str(version):
        return 200, {"version": version, "sin_cambios": True}
    return 200, salon.carta(almacen.listar(CFG, ctx.L, salon.PREFIJO_PRODUCTO), version)


@app.ruta("POST /locales/{local_id}/mesas/{mesa_id}/bloqueo", escritura=True)
def bloqueo(peticion):
    return api.ejecutar_http(peticion, salon.BLOQUEO, peticion.cuerpo_con_ruta("local_id"))


@app.ruta("POST /locales/{local_id}/mesas/{mesa_id}/garzon", escritura=True)
def garzon(peticion):
    return api.ejecutar_http(peticion, salon.ASIGNAR_GARZON, peticion.cuerpo_con_ruta("local_id"))


lambda_handler = app
