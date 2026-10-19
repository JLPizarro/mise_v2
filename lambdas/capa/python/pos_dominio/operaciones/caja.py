"""Caja: registrar pago (uno o varios medios), finalizar venta, turno, arqueo ciego y retiros.

Correcciones respecto del local (pruebas en tests/dominio/test_caja.py):
D6 el saldo se valida bajo la versión del pedido (sin sobrepagos concurrentes) · D7 todo pago
pertenece a un pedido · D8 efectivo recibido, vuelto y documento llegan al servidor · D9 el pago
mixto es un solo comando atómico · D12 código inválido = 403, no 401 · D13 el autorizador se elige ·
D23 un ítem repetido en la selección se suma antes de validar.
"""

import re

from pos_dominio import autorizacion, claves, dinero, roles, tiempo, validacion as v, vistas
from pos_dominio.cambios import Borrar, Crear, Evento, Guardar, Rechazo, Resultado, Sumar, existe, igual
from pos_dominio.errores import Conflicto, NoEncontrado, Prohibido, Validacion
from pos_dominio.modelos import (
    METODOS_PAGO, TIPOS_DIVISION, TIPOS_DOCUMENTO, ConfigLocal, MesaEstado, Pago, Turno,
)
from pos_dominio.operaciones.base import Operacion, reemplazar
from pos_dominio.operaciones.pedidos import exigir_pedido, guardar_mesa, guardar_pedido, item_cambio

OP = claves.TABLA_OPERACION
MAX_MEDIOS = 2            # FormularioPago.tsx: pago simple o mixto con exactamente 2 medios
MAX_ITEMS_COBRADOS = 80
_RUT = re.compile(r"^\d{7,8}-[\dK]$")


def _turno_no_abierto() -> Conflicto:
    return Conflicto("No hay un turno de caja abierto. Abre un turno antes de registrar pagos.",
                     codigo="TURNO_NO_ABIERTO")


def guardar_turno(ctx, turno: Turno) -> Guardar:
    return Guardar(tabla=OP, pk=claves.turno(ctx.L, turno.turno_id), sk=claves.SK_TURNO,
                   atributos={"tipo_item": "TURNO", **turno.a_atributos()}, version_leida=turno.version)


def sumar_turno(ctx, turno_id: str, incrementos: dict) -> Sumar:
    # ADD conmutativo: dos cobros simultáneos no chocan entre sí, pero sí suben la versión, así que
    # un conteo o cierre leído antes de un cobro se vuelve a calcular.
    return Sumar(tabla=OP, pk=claves.turno(ctx.L, turno_id), sk=claves.SK_TURNO, incrementos=incrementos,
                 condicion=igual("estado", "abierto"), al_fallar=_turno_no_abierto())


# --- registrar pago -----------------------------------------------------------------------------------

def leer_pago(almacen, ctx, cuerpo):
    pedido_id = v.identificador(v.objeto(cuerpo), "pedido_id")
    return {"turno": almacen.turno_abierto(ctx.L), "pedido": almacen.pedido(ctx.L, pedido_id)}


def _validar_medio(datos, indice: int) -> dict:
    campo = f"medios[{indice}]"
    datos = v.objeto(datos, campo)
    metodo = datos.get("metodo")
    if metodo not in METODOS_PAGO:
        raise Validacion("metodo de pago inválido", codigo="METODO_INVALIDO", detalle={"campo": campo})
    monto = v.entero(datos, "monto", minimo=1)
    propina = v.entero(datos, "propina", requerido=False, defecto=0, minimo=0)
    medio = {"metodo": metodo, "monto": monto, "propina": propina, "codigo_autorizacion_pos": None,
             "efectivo_recibido": None, "vuelto": None}
    if metodo in ("debito", "credito"):
        codigo = v.texto(datos, "codigo_autorizacion_pos", requerido=False, max_largo=64)
        if not codigo:
            raise Validacion("codigo_autorizacion_pos es requerido para tarjetas", codigo="CODIGO_POS_REQUERIDO",
                             detalle={"campo": campo})
        medio["codigo_autorizacion_pos"] = codigo
    if metodo == "efectivo":
        # FormularioPago.tsx: el efectivo recibido debe cubrir monto + propina de ese medio.
        recibido = v.entero(datos, "efectivo_recibido", minimo=0)
        if recibido < monto + propina:
            raise Validacion("El efectivo recibido no alcanza para el monto y la propina",
                             codigo="EFECTIVO_INSUFICIENTE", detalle={"campo": campo})
        medio["efectivo_recibido"] = recibido
        medio["vuelto"] = recibido - monto - propina
    return medio


def decidir_pago(estado, ctx, cuerpo) -> Resultado:
    medios = [_validar_medio(m, i) for i, m in enumerate(v.lista(cuerpo, "medios", minimo=1, maximo=MAX_MEDIOS))]
    division = v.uno_de(cuerpo, "tipo_division", TIPOS_DIVISION, requerido=False, defecto="completa")
    seleccion_cruda = v.lista(cuerpo, "items_cobrados", requerido=False, maximo=MAX_ITEMS_COBRADOS)

    turno = estado["turno"]
    if turno is None:
        raise _turno_no_abierto()
    pedido = exigir_pedido(estado["pedido"])
    if pedido.estado == "cerrado":
        raise Conflicto("El pedido ya está cerrado", codigo="PEDIDO_CERRADO")

    monto_total = sum(m["monto"] for m in medios)
    if monto_total > pedido.saldo:
        raise Validacion("El monto excede el saldo pendiente del pedido", codigo="MONTO_EXCEDE_SALDO",
                         detalle={"saldo": pedido.saldo})

    seleccion: dict[str, int] = {}
    if division == "items":
        if not seleccion_cruda:
            raise Validacion("Indica los ítems que se cobran", codigo="ITEMS_REQUERIDOS")
        pares = []
        for i, dato in enumerate(seleccion_cruda):
            dato = v.objeto(dato, f"items_cobrados[{i}]")
            item_id = v.identificador(dato, "item_id")
            if pedido.item(item_id) is None:
                raise Validacion("Uno de los ítems no pertenece a este pedido", codigo="ITEM_AJENO")
            pares.append((item_id, v.entero(dato, "cantidad", minimo=1)))
        seleccion = dinero.agrupar_seleccion(pares)
        disponibles = {i.item_id: (i.sin_cobrar, i.precio_unitario) for i in pedido.items}
        esperado = dinero.monto_por_items(disponibles, seleccion, pedido.saldo)
        if monto_total != esperado:
            # Antes el servidor aceptaba cualquier monto con cualquier selección.
            raise Validacion("El monto no corresponde a los ítems seleccionados", codigo="MONTO_NO_CORRESPONDE",
                             detalle={"esperado": esperado})
    elif seleccion_cruda:
        raise Validacion("items_cobrados solo se usa con tipo_division = items", codigo="ITEMS_FUERA_DE_DIVISION")

    pagos = []
    for indice, medio in enumerate(medios):
        pagos.append(Pago(
            pago_id=ctx.nuevo_id(), turno_id=turno.turno_id, metodo=medio["metodo"], monto=medio["monto"],
            propina=medio["propina"], tipo_division=division, usuario_id=ctx.usuario_id, fecha=ctx.ahora_iso,
            codigo_autorizacion_pos=medio["codigo_autorizacion_pos"],
            efectivo_recibido=medio["efectivo_recibido"], vuelto=medio["vuelto"],
            # Como en el local, la selección de ítems va en el primer medio para no duplicarla.
            items_cobrados=[{"item_id": k, "cantidad": c} for k, c in seleccion.items()] if indice == 0 else [],
        ))

    cambios = []
    for item_id, cantidad in seleccion.items():
        item = pedido.item(item_id)
        item.cobrado += cantidad
        cambios.append(item_cambio(ctx, pedido.pedido_id, item, nuevo=False))
    pedido.pagado += monto_total
    pedido.propina_total += sum(m["propina"] for m in medios)
    pedido.pagos.extend(pagos)
    cambios.append(guardar_pedido(ctx, pedido))
    for pago in pagos:
        cambios.append(Crear(tabla=OP, pk=claves.pedido(ctx.L, pedido.pedido_id), sk=claves.sk_pago(pago.pago_id),
                             atributos={"tipo_item": "PAGO", **pago.a_atributos()}))
    incrementos: dict[str, int] = {"n_pagos": len(pagos)}
    for pago in pagos:
        campo = f"tot_{pago.metodo}"
        incrementos[campo] = incrementos.get(campo, 0) + pago.monto + pago.propina
    cambios.append(sumar_turno(ctx, turno.turno_id, incrementos))

    return Resultado(
        {"pagos": [vistas.pago(p) for p in pagos],
         "pedido": {"pedido_id": pedido.pedido_id, "total": pedido.total, "pagado": pedido.pagado,
                    "saldo": pedido.saldo, "propina_total": pedido.propina_total}},
        http=201, cambios=cambios,
        eventos=[Evento("pago.registrado", {
            "pedido_id": pedido.pedido_id, "mesa_id": pedido.mesa_id, "turno_id": turno.turno_id,
            "tipo_division": division, "saldo": pedido.saldo,
            "pagos": [{"pago_id": p.pago_id, "metodo": p.metodo, "monto": p.monto, "propina": p.propina}
                      for p in pagos]})],
    )


# --- finalizar venta ------------------------------------------------------------------------------------

def leer_finalizar(almacen, ctx, cuerpo):
    pedido_id = v.identificador(v.objeto(cuerpo), "pedido_id")
    pedido = almacen.pedido(ctx.L, pedido_id)
    return {"pedido": pedido, "turno": almacen.turno_abierto(ctx.L),
            "mesa": almacen.mesa_estado(ctx.L, pedido.mesa_id) if pedido else None}


def _documento(cuerpo) -> dict:
    tipo = v.uno_de(cuerpo, "tipo_documento", TIPOS_DOCUMENTO)
    if tipo == "boleta":
        return {"tipo": "boleta"}
    receptor = v.objeto(cuerpo.get("receptor"), "receptor")
    # Mismo criterio que DatosFactura.tsx: formato de RUT y razón social de al menos 2 caracteres.
    rut = v.texto(receptor, "rut", max_largo=20).replace(".", "").replace(" ", "").upper()
    if not _RUT.match(rut):
        raise Validacion("RUT inválido", codigo="RUT_INVALIDO")
    razon_social = v.texto(receptor, "razon_social", max_largo=200)
    if len(razon_social) < 2:
        raise Validacion("Razón social inválida", codigo="RAZON_SOCIAL_INVALIDA")
    return {"tipo": "factura", "receptor": {"rut": rut, "razon_social": razon_social}}


def decidir_finalizar(estado, ctx, cuerpo) -> Resultado:
    pedido = exigir_pedido(estado["pedido"])
    if pedido.estado == "cerrado":
        # Idempotente por estado: si la PWA reintenta con otro comando tras perder la respuesta.
        return Resultado({"pedido": vistas.pedido(pedido), "documento": pedido.documento})
    turno = estado["turno"]
    if turno is None:
        raise _turno_no_abierto()
    if pedido.pagado < pedido.total:
        raise Validacion("El pedido todavía tiene saldo pendiente, no se puede finalizar",
                         codigo="SALDO_PENDIENTE", detalle={"saldo": pedido.saldo})
    hay_venta = pedido.total > 0
    documento = _documento(cuerpo) if hay_venta else None

    pedido.estado, pedido.cerrado_en = "cerrado", ctx.ahora_iso
    pedido.documento, pedido.turno_cierre_id = documento, turno.turno_id
    cambios = [guardar_pedido(ctx, pedido)]
    mesa = estado["mesa"]
    if mesa is not None and mesa.pedido_id == pedido.pedido_id:
        libre = MesaEstado(mesa_id=mesa.mesa_id, estado="libre", version=mesa.version)
        cambios.append(guardar_mesa(ctx, libre, pedido_esperado=pedido.pedido_id))
    cambios.append(sumar_turno(ctx, turno.turno_id, {"n_ventas": 1 if hay_venta else 0, "tot_ventas": pedido.total}))

    if not hay_venta:
        # M14: una mesa sin consumo se libera sin documento tributario.
        return Resultado({"pedido": vistas.pedido(pedido), "documento": None}, cambios=cambios,
                         eventos=[Evento("pedido.cerrado_sin_venta", {"pedido_id": pedido.pedido_id,
                                                                      "mesa_id": pedido.mesa_id})])

    venta = {
        "venta_id": pedido.pedido_id, "pedido_id": pedido.pedido_id, "mesa_id": pedido.mesa_id,
        "turno_id": turno.turno_id, "fecha_operativa": turno.fecha_operativa, "garzon_id": pedido.garzon_id,
        "cajero_id": ctx.usuario_id, "total": pedido.total, "propina_total": pedido.propina_total,
        "documento": documento, "cerrado_en": pedido.cerrado_en,
        "pagos": [{"metodo": p.metodo, "monto": p.monto, "propina": p.propina} for p in pedido.pagos],
        "items": [{"nombre": i.nombre, "modificador": i.modificador_nombre, "categoria": i.categoria,
                   "cantidad": i.cantidad, "precio_unitario": i.precio_unitario, "subtotal": i.subtotal}
                  for i in sorted(pedido.items, key=lambda i: i.item_id)],
    }
    dte = {"tipo_item": "DTE", "venta_id": pedido.pedido_id, "pedido_id": pedido.pedido_id,
           "turno_id": turno.turno_id, "estado": "pendiente", "tipo": documento["tipo"],
           "receptor": documento.get("receptor"), "total": pedido.total, "intentos": 0, "creado_en": ctx.ahora_iso,
           "detalle": {"items": venta["items"], "total": pedido.total, "propina_total": pedido.propina_total},
           "version": 1, "GSI1PK": claves.VIGILAR_DTE, "GSI1SK": f"{ctx.ahora_iso}#{pedido.pedido_id}"}
    cambios.append(Crear(tabla=OP, pk=claves.turno(ctx.L, turno.turno_id), sk=claves.sk_dte(pedido.pedido_id),
                         atributos=dte))
    return Resultado({"pedido": vistas.pedido(pedido), "documento": {"tipo": documento["tipo"], "estado": "pendiente"}},
                     cambios=cambios, eventos=[Evento("venta.cerrada", venta)])


# --- turno ------------------------------------------------------------------------------------------

def leer_turno_abierto(almacen, ctx, cuerpo):
    return {"turno": almacen.turno_abierto(ctx.L)}


def decidir_abrir_turno(estado, ctx, cuerpo) -> Resultado:
    monto = v.entero(v.objeto(cuerpo), "monto_apertura", requerido=False, defecto=0, minimo=0)
    if estado["turno"] is not None:
        raise Conflicto("Ya hay un turno de caja abierto", codigo="TURNO_YA_ABIERTO")
    turno = Turno(turno_id=ctx.nuevo_id(), usuario_apertura_id=ctx.usuario_id, monto_apertura=monto,
                  abierto_en=ctx.ahora_iso, fecha_operativa=tiempo.fecha_operativa(ctx.ahora))
    puntero = {"tipo_item": "TURNO_ABIERTO", "turno_id": turno.turno_id, "abierto_en": turno.abierto_en,
               "GSI1PK": claves.VIGILAR_TURNO, "GSI1SK": f"{turno.abierto_en}#{turno.turno_id}"}
    indice = {"tipo_item": "TURNO_INDICE", "turno_id": turno.turno_id, "fecha_operativa": turno.fecha_operativa,
              "estado": "abierto", "abierto_en": turno.abierto_en}
    return Resultado(
        vistas.turno(turno), http=201,
        cambios=[
            # attribute_not_exists sobre TURNO_ABIERTO garantiza un solo turno abierto por local.
            Crear(tabla=OP, pk=claves.caja(ctx.L), sk=claves.SK_TURNO_ABIERTO, atributos=puntero,
                  al_fallar=Conflicto("Ya hay un turno de caja abierto", codigo="TURNO_YA_ABIERTO")),
            guardar_turno(ctx, turno),
            Crear(tabla=OP, pk=claves.caja(ctx.L), sk=claves.sk_indice_turno(turno.turno_id), atributos=indice),
        ],
        eventos=[Evento("turno.abierto", {"turno_id": turno.turno_id, "monto_apertura": monto,
                                          "fecha_operativa": turno.fecha_operativa})],
    )


def leer_turno(almacen, ctx, cuerpo):
    turno_id = v.identificador(v.objeto(cuerpo), "turno_id")
    return {"turno": almacen.turno(ctx.L, turno_id), "config": almacen.config_local(ctx.L)}


def _exigir_turno_abierto(turno: Turno | None) -> Turno:
    if turno is None:
        raise NoEncontrado("Turno no encontrado", codigo="TURNO_NO_ENCONTRADO")
    if turno.estado != "abierto":
        raise Conflicto("El turno ya está cerrado", codigo="TURNO_CERRADO")
    return turno


def _config(estado) -> ConfigLocal:
    # Si faltara la configuración del local, rige el valor por defecto del requisito RF-C12:
    # 2 % del esperado o $5.000, el mayor.
    return estado.get("config") or ConfigLocal(nombre_local="", marca="")


def decidir_conteo(estado, ctx, cuerpo) -> Resultado:
    monto = v.entero(cuerpo, "monto", minimo=0)
    turno = _exigir_turno_abierto(estado["turno"])
    es_segundo = turno.requiere_segundo_conteo and turno.segundo_conteo is None
    if not es_segundo and turno.primer_conteo is not None:
        raise Conflicto("El primer conteo ya fue registrado", codigo="CONTEO_YA_REGISTRADO")

    esperado = turno.efectivo_esperado
    config = _config(estado)
    umbral = dinero.umbral_diferencia(esperado, config.umbral_diferencia_pb, config.umbral_diferencia_minimo)
    if es_segundo:
        turno.segundo_conteo = monto
        requiere = False
    else:
        turno.primer_conteo = monto
        requiere = abs(monto - esperado) > umbral
        turno.requiere_segundo_conteo = requiere

    return Resultado(
        # Arqueo ciego: la respuesta no revela el esperado ni la diferencia.
        {"turno": vistas.turno(turno), "requiere_segundo_conteo": requiere, "conteo_completado": not requiere},
        cambios=[guardar_turno(ctx, turno)],
        eventos=[Evento("conteo.registrado", {"turno_id": turno.turno_id, "numero": 2 if es_segundo else 1,
                                              "monto": monto, "esperado": esperado, "umbral": umbral,
                                              "requiere_segundo_conteo": requiere})],
    )


def decidir_conciliacion(estado, ctx, cuerpo) -> Resultado:
    debito = v.entero(cuerpo, "total_debito_pos", minimo=0)
    credito = v.entero(cuerpo, "total_credito_pos", minimo=0)
    notas = v.entero(cuerpo, "total_notas_credito_pos", requerido=False, defecto=0, minimo=0)
    turno = _exigir_turno_abierto(estado["turno"])
    # Como en el local, se puede corregir mientras el turno siga abierto (D17).
    turno.conciliacion = {"total_debito_pos": debito, "total_credito_pos": credito,
                          "total_notas_credito_pos": notas}
    return Resultado({"turno": vistas.turno(turno)}, cambios=[guardar_turno(ctx, turno)],
                     eventos=[Evento("conciliacion.registrada", {"turno_id": turno.turno_id, **turno.conciliacion})])


def decidir_cerrar(estado, ctx, cuerpo) -> Resultado:
    turno = _exigir_turno_abierto(estado["turno"])
    if turno.primer_conteo is None:
        raise Conflicto("Falta registrar el conteo de efectivo", codigo="FALTA_CONTEO")
    if turno.requiere_segundo_conteo and turno.segundo_conteo is None:
        raise Conflicto("Falta registrar el segundo conteo de efectivo", codigo="FALTA_SEGUNDO_CONTEO")
    if turno.conciliacion is None:
        raise Conflicto("Falta registrar la conciliación del terminal", codigo="FALTA_CONCILIACION")

    esperado = turno.efectivo_esperado
    definitivo = turno.segundo_conteo if turno.segundo_conteo is not None else turno.primer_conteo
    config = _config(estado)
    umbral = dinero.umbral_diferencia(esperado, config.umbral_diferencia_pb, config.umbral_diferencia_minimo)
    resultado = {
        "efectivo_esperado": esperado, "conteo_definitivo": definitivo, "diferencia_efectivo": definitivo - esperado,
        "total_efectivo_mise": turno.tot_efectivo, "total_debito_mise": turno.tot_debito,
        "total_credito_mise": turno.tot_credito, "total_transferencia_mise": turno.tot_transferencia,
        "total_retiros": turno.tot_retiros, "umbral": umbral, "fuera_de_umbral": abs(definitivo - esperado) > umbral,
        "n_ventas": turno.n_ventas, "total_ventas": turno.tot_ventas,
    }
    turno.estado, turno.resultado = "cerrado", resultado
    turno.usuario_cierre_id, turno.cerrado_en = ctx.usuario_id, ctx.ahora_iso
    indice = {"tipo_item": "TURNO_INDICE", "turno_id": turno.turno_id, "fecha_operativa": turno.fecha_operativa,
              "estado": "cerrado", "abierto_en": turno.abierto_en, "cerrado_en": turno.cerrado_en,
              "diferencia_efectivo": resultado["diferencia_efectivo"], "total_ventas": turno.tot_ventas}
    return Resultado(
        {"turno": vistas.turno(turno), **resultado},
        cambios=[
            guardar_turno(ctx, turno),
            Borrar(tabla=OP, pk=claves.caja(ctx.L), sk=claves.SK_TURNO_ABIERTO,
                   condicion=igual("turno_id", turno.turno_id)),
            reemplazar(OP, claves.caja(ctx.L), claves.sk_indice_turno(turno.turno_id), indice),
        ],
        eventos=[Evento("turno.cerrado", {"turno_id": turno.turno_id, "fecha_operativa": turno.fecha_operativa,
                                          "usuario_cierre_id": ctx.usuario_id, "resultado": resultado})],
    )


# --- retiro con autorización ------------------------------------------------------------------------

def leer_retiro(almacen, ctx, cuerpo):
    autorizador_id = v.identificador(v.objeto(cuerpo), "autorizador_id")
    return {"turno": almacen.turno_abierto(ctx.L),
            "autorizador": almacen.membresia(autorizador_id, ctx.tenant_id, ctx.local_id),
            "bloqueo": almacen.bloqueo(ctx.L, autorizador_id)}


def decidir_retiro(estado, ctx, cuerpo):
    monto = v.entero(cuerpo, "monto", minimo=1)
    motivo = v.texto(cuerpo, "motivo", max_largo=200)
    codigo = cuerpo.get("codigo")
    turno = estado["turno"]
    if turno is None:
        raise Conflicto("No hay un turno de caja abierto", codigo="TURNO_NO_ABIERTO")
    autorizador = estado["autorizador"]
    if autorizador is None or not autorizador.activa or not roles.permitido(autorizador.rol, "autorizar") \
            or not autorizador.pin_hash:
        raise Prohibido("La persona elegida no puede autorizar retiros", codigo="AUTORIZADOR_INVALIDO")

    ahora = tiempo.epoch(ctx.ahora)
    bloqueo = estado["bloqueo"]
    autorizacion.verificar_no_bloqueado(bloqueo, ahora)
    if not autorizacion.verificar(codigo if isinstance(codigo, str) else "", autorizador.pin_hash,
                                  autorizador.pin_sal, autorizador.pin_iter):
        nuevo = autorizacion.registrar_fallo(bloqueo, ahora)
        atributos = {"tipo_item": "BLOQUEO", **nuevo.a_atributos(),
                     "expira_en": max(nuevo.ventana_hasta, nuevo.bloqueado_hasta) + 60}
        atributos.pop("version")
        restantes = autorizacion.intentos_restantes(nuevo)
        return Rechazo(
            error=Prohibido("Código de autorización inválido", codigo="CODIGO_AUTORIZACION_INVALIDO",
                            detalle={"intentos_restantes": restantes}),
            cambios=[Guardar(tabla=OP, pk=claves.autorizaciones(ctx.L), sk=claves.sk_bloqueo(autorizador.sub),
                             atributos=atributos, version_leida=bloqueo.version if bloqueo else 0)],
            eventos=[Evento("autorizacion.rechazada", {"accion": "caja.retiro", "autorizador_id": autorizador.sub,
                                                       "solicitante_id": ctx.usuario_id, "intentos": nuevo.intentos,
                                                       "bloqueado": restantes == 0})],
        )

    retiro_id = ctx.nuevo_id()
    retiro = {"tipo_item": "RETIRO", "retiro_id": retiro_id, "turno_id": turno.turno_id,
              "usuario_id": ctx.usuario_id, "autorizado_por": autorizador.sub, "monto": monto, "motivo": motivo,
              "creado_en": ctx.ahora_iso}
    cambios = [Crear(tabla=OP, pk=claves.turno(ctx.L, turno.turno_id), sk=claves.sk_retiro(retiro_id), atributos=retiro),
               sumar_turno(ctx, turno.turno_id, {"tot_retiros": monto})]
    if bloqueo is not None:
        cambios.append(Borrar(tabla=OP, pk=claves.autorizaciones(ctx.L), sk=claves.sk_bloqueo(autorizador.sub)))
    respuesta = {k: val for k, val in retiro.items() if k != "tipo_item"}
    return Resultado(respuesta, http=201, cambios=cambios, eventos=[
        Evento("retiro.registrado", respuesta),
        Evento("autorizacion.concedida", {"accion": "caja.retiro", "autorizador_id": autorizador.sub,
                                          "solicitante_id": ctx.usuario_id, "referencia": retiro_id}),
    ])


# --- documentos, conflictos e impresiones retenidas -------------------------------------------------

def vista_dte(dte: dict) -> dict:
    return {k: dte.get(k) for k in ("venta_id", "turno_id", "estado", "tipo", "receptor", "total", "folio", "timbre",
                                    "motivo_rechazo", "intentos", "creado_en", "emitido_en")}


def leer_documento(almacen, ctx, cuerpo):
    venta_id = v.identificador(v.objeto(cuerpo), "venta_id")
    pedido = almacen.pedido(ctx.L, venta_id)
    dte = None
    if pedido and pedido.turno_cierre_id:
        dte = almacen.obtener(OP, claves.turno(ctx.L, pedido.turno_cierre_id), claves.sk_dte(venta_id))
    config = almacen.config_local(ctx.L)
    return {"dte": dte, "config": config, "impresoras": almacen.impresoras(ctx.L)}


def decidir_reimprimir(estado, ctx, cuerpo) -> Resultado:
    dte = estado["dte"]
    if dte is None:
        raise NoEncontrado("Documento no encontrado", codigo="DOCUMENTO_NO_ENCONTRADO")
    if dte["estado"] != "emitido":
        raise Conflicto("El documento todavía no está emitido", codigo="DOCUMENTO_NO_EMITIDO",
                        detalle={"estado": dte["estado"]})
    config = estado["config"]
    impresora = estado["impresoras"].get(config.impresora_caja_id) if config and config.impresora_caja_id else None
    if impresora is None or not impresora.activa:
        raise Conflicto("La caja no tiene una impresora activa configurada", codigo="SIN_IMPRESORA_DE_CAJA")
    trabajo = trabajo_documento(dte, impresora.impresora_id, ctx.nuevo_id(), ctx.ahora_iso, reimpresion=True)
    return Resultado({"venta_id": dte["venta_id"], "trabajo_id": trabajo["trabajo_id"], "estado": "encolada"},
                     cambios=[Crear(tabla=OP, pk=claves.impresora(ctx.L, impresora.impresora_id),
                                    sk=claves.sk_trabajo_pendiente(trabajo["trabajo_id"]), atributos=trabajo)],
                     eventos=[Evento("documento.reimpreso", {"venta_id": dte["venta_id"], "folio": dte.get("folio")})])


def trabajo_documento(dte: dict, impresora_id: str, trabajo_id: str, ahora_iso: str, *, reimpresion: bool = False) -> dict:
    return {"tipo_item": "TRABAJO_IMPRESION", "trabajo_id": trabajo_id, "tipo": dte["tipo"],
            "tipo_documento": dte["tipo"], "impresora_id": impresora_id, "venta_id": dte["venta_id"],
            "folio": dte.get("folio"), "timbre": dte.get("timbre"), "receptor": dte.get("receptor"),
            "emitido_en": dte.get("emitido_en"), "detalle": dte.get("detalle", {}), "creado_en": ahora_iso,
            "estado": "pendiente", "origen": "normal", "reimpresion": reimpresion,
            "GSI1PK": claves.VIGILAR_IMPRESION, "GSI1SK": f"{ahora_iso}#{trabajo_id}"}


def leer_conflicto(almacen, ctx, cuerpo):
    conflicto_id = v.identificador(v.objeto(cuerpo), "conflicto_id")
    return {"conflicto": almacen.obtener(OP, claves.conflictos(ctx.L), f"CONFLICTO#{conflicto_id}")}


def decidir_resolver_conflicto(estado, ctx, cuerpo) -> Resultado:
    resolucion = v.uno_de(cuerpo, "resolucion", ("resuelto", "descartado"))
    nota = v.texto(cuerpo, "nota", requerido=False, max_largo=300)
    conflicto = estado["conflicto"]
    if conflicto is None:
        raise NoEncontrado("Conflicto no encontrado", codigo="CONFLICTO_NO_ENCONTRADO")
    if conflicto["estado"] != "abierto":
        raise Conflicto("El conflicto ya fue resuelto", codigo="CONFLICTO_YA_RESUELTO")
    atributos = {k: val for k, val in conflicto.items() if k not in ("PK", "SK", "version")}
    atributos.update({"estado": resolucion, "nota": nota, "resuelto_por": ctx.usuario_id, "resuelto_en": ctx.ahora_iso})
    atributos = {k: val for k, val in atributos.items() if val is not None}
    return Resultado({k: val for k, val in atributos.items() if k != "tipo_item"}, cambios=[
        Guardar(tabla=OP, pk=claves.conflictos(ctx.L), sk=conflicto["SK"], atributos=atributos,
                version_leida=conflicto.get("version", 1))],
        eventos=[Evento("conflicto.resuelto", {"conflicto_id": conflicto["conflicto_id"], "resolucion": resolucion})])


def leer_retenido(almacen, ctx, cuerpo):
    trabajo_id = v.identificador(v.objeto(cuerpo), "trabajo_id")
    return {"trabajo": almacen.obtener(OP, claves.retenidos(ctx.L), claves.sk_retenido(trabajo_id))}


def _decidir_retenido(liberar: bool):
    def decidir(estado, ctx, cuerpo) -> Resultado:
        trabajo = estado["trabajo"]
        if trabajo is None:
            raise NoEncontrado("Impresión retenida no encontrada", codigo="TRABAJO_NO_ENCONTRADO")
        borrar = Borrar(tabla=OP, pk=claves.retenidos(ctx.L), sk=trabajo["SK"], condicion=existe())
        if not liberar:
            return Resultado({"trabajo_id": trabajo["trabajo_id"], "estado": "descartado"}, cambios=[borrar],
                             eventos=[Evento("impresion.descartada", {"trabajo_id": trabajo["trabajo_id"]})])
        atributos = {k: val for k, val in trabajo.items() if k not in ("PK", "SK")}
        atributos.update({"estado": "pendiente", "liberado_por": ctx.usuario_id, "GSI1PK": claves.VIGILAR_IMPRESION,
                          "GSI1SK": f"{ctx.ahora_iso}#{trabajo['trabajo_id']}"})
        return Resultado({"trabajo_id": trabajo["trabajo_id"], "estado": "encolada"}, cambios=[
            borrar, Crear(tabla=OP, pk=claves.impresora(ctx.L, trabajo["impresora_id"]),
                          sk=claves.sk_trabajo_pendiente(trabajo["trabajo_id"]), atributos=atributos)],
            eventos=[Evento("impresion.liberada", {"trabajo_id": trabajo["trabajo_id"]})])
    return decidir


REIMPRIMIR = Operacion("caja.reimprimir", "caja.cobrar", leer_documento, decidir_reimprimir)
RESOLVER_CONFLICTO = Operacion("caja.resolver_conflicto", "caja.contingencia", leer_conflicto, decidir_resolver_conflicto)
LIBERAR_RETENIDO = Operacion("caja.liberar_impresion", "caja.contingencia", leer_retenido, _decidir_retenido(True))
DESCARTAR_RETENIDO = Operacion("caja.descartar_impresion", "caja.contingencia", leer_retenido, _decidir_retenido(False))

REGISTRAR_PAGO = Operacion("caja.registrar_pago", "caja.cobrar", leer_pago, decidir_pago)
FINALIZAR = Operacion("caja.finalizar", "caja.cobrar", leer_finalizar, decidir_finalizar)
ABRIR_TURNO = Operacion("caja.abrir_turno", "caja.turno", leer_turno_abierto, decidir_abrir_turno)
CONTEO = Operacion("caja.conteo", "caja.turno", leer_turno, decidir_conteo)
CONCILIACION = Operacion("caja.conciliacion", "caja.turno", leer_turno, decidir_conciliacion)
CERRAR_TURNO = Operacion("caja.cerrar_turno", "caja.turno", leer_turno, decidir_cerrar)
RETIRO = Operacion("caja.retiro", "caja.retiro", leer_retiro, decidir_retiro)
