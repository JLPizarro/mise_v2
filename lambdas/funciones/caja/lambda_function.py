"""Función `caja`: cobro, cierre de venta, turno, arqueo ciego, retiros, documentos tributarios,
bandeja de conflictos e impresiones retenidas por contingencia.

Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, LOG_LEVEL (opcional)
Memoria sugerida: 512 MB (la verificación del código de autorización usa PBKDF2 de 200.000 iteraciones).
"""

from pos_dominio import claves, roles, vistas
from pos_dominio.errores import NoEncontrado
from pos_dominio.infra import api, aws, http
from pos_dominio.operaciones import caja as C

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION")
app = http.Aplicacion("caja")
OP = claves.TABLA_OPERACION


def _cuerpo(peticion):
    return peticion.cuerpo_con_ruta("local_id")


def _escribir(operacion):
    return lambda peticion: api.ejecutar_http(peticion, operacion, _cuerpo(peticion))


# --- escrituras ---------------------------------------------------------------------------------------

for ruta, operacion in {
    "POST /locales/{local_id}/pedidos/{pedido_id}/pagos": C.REGISTRAR_PAGO,
    "POST /locales/{local_id}/pedidos/{pedido_id}/finalizar": C.FINALIZAR,
    "POST /locales/{local_id}/caja/turnos": C.ABRIR_TURNO,
    "POST /locales/{local_id}/caja/turnos/{turno_id}/conteo": C.CONTEO,
    "POST /locales/{local_id}/caja/turnos/{turno_id}/conciliacion": C.CONCILIACION,
    "POST /locales/{local_id}/caja/turnos/{turno_id}/cerrar": C.CERRAR_TURNO,
    "POST /locales/{local_id}/caja/retiros": C.RETIRO,
    "POST /locales/{local_id}/caja/documentos/{venta_id}/reimprimir": C.REIMPRIMIR,
    "POST /locales/{local_id}/caja/conflictos/{conflicto_id}/resolver": C.RESOLVER_CONFLICTO,
    "POST /locales/{local_id}/caja/impresiones-retenidas/{trabajo_id}/liberar": C.LIBERAR_RETENIDO,
    "POST /locales/{local_id}/caja/impresiones-retenidas/{trabajo_id}/descartar": C.DESCARTAR_RETENIDO,
}.items():
    app.ruta(ruta, escritura=True)(_escribir(operacion))


# --- lecturas -----------------------------------------------------------------------------------------

@app.ruta("GET /locales/{local_id}/caja/turno")
def turno_actual(peticion):
    ctx = api.contexto(peticion, accion="caja.turno")
    turno = aws.almacen().turno_abierto(ctx.L)
    if turno is None:
        raise NoEncontrado("No hay un turno de caja abierto", codigo="TURNO_NO_ABIERTO")
    return 200, vistas.turno(turno)


@app.ruta("GET /locales/{local_id}/caja/pendientes")
def pendientes(peticion):
    """Mesas en precuenta con su pedido completo (antes: N consultas desde el navegador)."""
    ctx = api.contexto(peticion, accion="caja.cobrar")
    almacen = aws.almacen()
    mesas = [m for m in almacen.listar(OP, claves.salon(ctx.L), "MESA#", consistente=True)
             if m.get("estado") == "precuenta" and m.get("pedido_id")]
    resultado = []
    for mesa in mesas:
        pedido = almacen.pedido(ctx.L, mesa["pedido_id"])
        if pedido is not None and pedido.estado == "precuenta":
            resultado.append({"mesa_id": mesa["mesa_id"], "pedido": vistas.pedido(pedido)})
    return 200, {"pendientes": resultado}


@app.ruta("GET /locales/{local_id}/caja/autorizadores")
def autorizadores(peticion):
    """Dueños y admins del local con código definido: la lista para elegir quién autoriza (M12)."""
    ctx = api.contexto(peticion, accion="caja.retiro")
    personas = [p for p in aws.almacen().personal(ctx.L)
                if p.get("tipo_item") == "MEMBRESIA" and p.get("estado") == "activo"
                and roles.permitido(p.get("rol", ""), "autorizar")]
    # El índice no proyecta el hash: se confirma que tenga código leyendo cada membresía.
    almacen = aws.almacen()
    lista = []
    for persona in personas:
        membresia = almacen.membresia(persona["sub"], ctx.tenant_id, ctx.local_id)
        if membresia and membresia.pin_hash:
            lista.append({"sub": membresia.sub, "nombre": membresia.nombre, "rol": membresia.rol})
    return 200, {"autorizadores": lista}


def _turno_consultado(peticion, ctx):
    turno_id = peticion.query.get("turno_id")
    if turno_id:
        return claves.validar_id(turno_id, "turno_id")
    turno = aws.almacen().turno_abierto(ctx.L)
    if turno is None:
        raise NoEncontrado("No hay un turno de caja abierto", codigo="TURNO_NO_ABIERTO")
    return turno.turno_id


@app.ruta("GET /locales/{local_id}/caja/retiros")
def retiros(peticion):
    ctx = api.contexto(peticion, accion="caja.retiro")
    turno_id = _turno_consultado(peticion, ctx)
    filas = aws.almacen().listar(OP, claves.turno(ctx.L, turno_id), "RETIRO#", consistente=True)
    return 200, {"turno_id": turno_id, "retiros": [{k: v for k, v in f.items() if k not in ("PK", "SK", "tipo_item")}
                                                    for f in sorted(filas, key=lambda f: f["SK"], reverse=True)]}


@app.ruta("GET /locales/{local_id}/caja/documentos")
def documentos(peticion):
    ctx = api.contexto(peticion, accion="caja.cobrar")
    turno_id = _turno_consultado(peticion, ctx)
    filas = aws.almacen().listar(OP, claves.turno(ctx.L, turno_id), "DTE#", consistente=True)
    return 200, {"turno_id": turno_id, "documentos": [C.vista_dte(f) for f in filas]}


@app.ruta("GET /locales/{local_id}/caja/documentos/{venta_id}")
def documento(peticion):
    ctx = api.contexto(peticion, accion="caja.cobrar")
    estado = C.leer_documento(aws.almacen(), ctx, {"venta_id": peticion.parametros["venta_id"]})
    if estado["dte"] is None:
        raise NoEncontrado("Documento no encontrado", codigo="DOCUMENTO_NO_ENCONTRADO")
    return 200, C.vista_dte(estado["dte"])


@app.ruta("GET /locales/{local_id}/caja/conflictos")
def conflictos(peticion):
    ctx = api.contexto(peticion, accion="caja.contingencia")
    filas = aws.almacen().listar(OP, claves.conflictos(ctx.L), "CONFLICTO#", consistente=True)
    solo_abiertos = peticion.query.get("todos") not in ("1", "true")
    return 200, {"conflictos": [{k: v for k, v in f.items() if k not in ("PK", "SK", "tipo_item")}
                                for f in filas if not solo_abiertos or f.get("estado") == "abierto"]}


@app.ruta("GET /locales/{local_id}/caja/impresiones-retenidas")
def retenidas(peticion):
    ctx = api.contexto(peticion, accion="caja.contingencia")
    filas = aws.almacen().listar(OP, claves.retenidos(ctx.L), "RET#", consistente=True)
    return 200, {"trabajos": [{k: v for k, v in f.items() if k not in ("PK", "SK", "tipo_item")} for f in filas]}


lambda_handler = app
