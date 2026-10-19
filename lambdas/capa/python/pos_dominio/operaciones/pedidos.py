"""Salón y comanda: abrir pedido, agregar, modificar y quitar ítems, enviar tanda, precuenta y
reabrir. Cada operación tiene `leer` (consultas) y `decidir` (puro).

Correcciones respecto del local (cada una con su prueba en tests/dominio/test_pedidos.py):
D1 no se agregan ítems a pedidos en precuenta o cerrados · D2 precuenta solo desde abierto ·
D3 un ítem enviado no se modifica ni se quita · D5 apertura atómica y sin mesas bloqueadas.
"""

from collections import OrderedDict

from pos_dominio import claves, ids, validacion as v, vistas
from pos_dominio.cambios import Crear, Evento, Guardar, Resultado, Borrar, igual
from pos_dominio.errores import Conflicto, NoEncontrado, Validacion
from pos_dominio.modelos import Item, MesaEstado, Pedido
from pos_dominio.operaciones.base import Operacion, reemplazar

MAX_LINEAS_PEDIDO = 300
MAX_LINEAS_TANDA = 80
MAX_CANTIDAD = 999
MAX_OBSERVACION = 500
OP = claves.TABLA_OPERACION


# --- utilidades -------------------------------------------------------------------------------------

def guardar_pedido(ctx, pedido: Pedido) -> Guardar:
    cambio = Guardar(tabla=OP, pk=claves.pedido(ctx.L, pedido.pedido_id), sk=claves.SK_PEDIDO,
                     atributos={"tipo_item": "PEDIDO", **pedido.a_atributos()}, version_leida=pedido.version)
    if pedido.version == 0:
        # Pedido nuevo con un ID propuesto por el cliente que ya existe: no tiene sentido releer.
        cambio.reintentar = False
        cambio.al_fallar = Conflicto("Ese identificador de pedido ya está en uso", codigo="PEDIDO_ID_EN_USO")
    return cambio


def id_propuesto(cuerpo: dict, campo: str, ctx) -> str:
    """El cliente puede proponer el ULID de una entidad nueva (pedido, ítem). Es lo que permite a la
    PWA seguir trabajando sobre un pedido abierto durante una contingencia, antes de que exista."""
    valor = cuerpo.get(campo)
    if valor is None:
        return ctx.nuevo_id()
    if not ids.es_ulid(valor):
        raise Validacion(f"{campo} debe ser un ULID", codigo="CAMPO_INVALIDO", detalle={"campo": campo})
    return valor


def guardar_mesa(ctx, mesa: MesaEstado, *, pedido_esperado: str | None = None) -> Guardar:
    atributos = {"tipo_item": "MESA_ESTADO", **mesa.a_atributos()}
    return Guardar(tabla=OP, pk=claves.salon(ctx.L), sk=claves.sk_mesa(mesa.mesa_id), atributos=atributos,
                   version_leida=mesa.version,
                   condicion_extra=igual("pedido_id", pedido_esperado) if pedido_esperado else None)


def item_cambio(ctx, pedido_id: str, item: Item, *, nuevo: bool):
    atributos = {"tipo_item": "ITEM", **item.a_atributos()}
    pk, sk = claves.pedido(ctx.L, pedido_id), claves.sk_item(item.item_id)
    if nuevo:
        return Crear(tabla=OP, pk=pk, sk=sk, atributos=atributos)
    return reemplazar(OP, pk, sk, atributos)


def exigir_pedido(pedido: Pedido | None) -> Pedido:
    if pedido is None:
        raise NoEncontrado("Pedido no encontrado", codigo="PEDIDO_NO_ENCONTRADO")
    return pedido


def exigir_abierto(pedido: Pedido) -> None:
    if pedido.estado == "precuenta":
        raise Conflicto("La mesa está en precuenta. Reábrela para modificar la comanda.",
                        codigo="PEDIDO_EN_PRECUENTA")
    if pedido.estado == "cerrado":
        raise Conflicto("El pedido ya está cerrado", codigo="PEDIDO_CERRADO")


def exigir_item(pedido: Pedido, item_id: str) -> Item:
    item = pedido.item(item_id)
    if item is None:
        raise NoEncontrado("Item no encontrado", codigo="ITEM_NO_ENCONTRADO")
    return item


def exigir_en_espera(item: Item) -> None:
    if item.estado != "en_espera":
        raise Conflicto("El ítem ya fue enviado a cocina y no se puede modificar",
                        codigo="ITEM_YA_ENVIADO")


def _vista_items(pedido: Pedido) -> list[dict]:
    return [vistas.item(i) for i in sorted(pedido.items, key=lambda i: i.item_id)]


def _datos_item(i: Item) -> dict:
    return {"item_id": i.item_id, "producto_id": i.producto_id, "nombre": i.nombre,
            "modificador": i.modificador_nombre, "cantidad": i.cantidad, "precio_unitario": i.precio_unitario,
            "observacion": i.observacion}


# --- abrir pedido -----------------------------------------------------------------------------------

def leer_abrir(almacen, ctx, cuerpo):
    mesa_id = v.identificador(v.objeto(cuerpo), "mesa_id")
    estado = almacen.mesa_estado(ctx.L, mesa_id)
    existente = almacen.pedido(ctx.L, estado.pedido_id) if estado and estado.pedido_id else None
    return {"mesa_id": mesa_id, "estructura": almacen.mesa_estructura(ctx.L, mesa_id), "estado": estado,
            "pedido": existente}


def decidir_abrir(estado, ctx, cuerpo) -> Resultado:
    estructura = estado["estructura"]
    if estructura is None or not estructura.activa:
        raise NoEncontrado("Mesa no encontrada", codigo="MESA_NO_ENCONTRADA")
    mesa = estado["estado"] or MesaEstado(mesa_id=estado["mesa_id"])
    existente = estado["pedido"]
    if existente is not None and existente.estado in ("abierto", "precuenta"):
        # Igual que el local: si la mesa ya tiene pedido, se devuelve ese.
        return Resultado(vistas.pedido(existente))
    if mesa.estado == "bloqueada":
        raise Conflicto("La mesa está bloqueada", codigo="MESA_BLOQUEADA")

    pedido = Pedido(pedido_id=id_propuesto(cuerpo, "pedido_id", ctx), mesa_id=mesa.mesa_id, garzon_id=ctx.usuario_id,
                    creado_en=ctx.ahora_iso, origen=ctx.origen)
    mesa_nueva = MesaEstado(mesa_id=mesa.mesa_id, estado="ocupada", pedido_id=pedido.pedido_id,
                            garzon_id=mesa.garzon_id or ctx.usuario_id, version=mesa.version)
    return Resultado(
        vistas.pedido(pedido), http=201,
        cambios=[guardar_pedido(ctx, pedido), guardar_mesa(ctx, mesa_nueva)],
        eventos=[Evento("pedido.abierto", {"pedido_id": pedido.pedido_id, "mesa_id": mesa.mesa_id,
                                           "garzon_id": mesa_nueva.garzon_id})],
    )


# --- agregar ítem -----------------------------------------------------------------------------------

def leer_agregar(almacen, ctx, cuerpo):
    datos = v.objeto(cuerpo)
    pedido_id = v.identificador(datos, "pedido_id")
    producto_id = v.identificador(datos, "producto_id")
    return {"pedido": almacen.pedido(ctx.L, pedido_id), "producto": almacen.producto(ctx.L, producto_id)}


def decidir_agregar(estado, ctx, cuerpo) -> Resultado:
    cantidad = v.entero(cuerpo, "cantidad", requerido=False, defecto=1, minimo=1, maximo=MAX_CANTIDAD)
    modificador_id = v.identificador(cuerpo, "modificador_id", requerido=False)
    observacion = v.texto(cuerpo, "observacion", requerido=False, max_largo=MAX_OBSERVACION)

    pedido = exigir_pedido(estado["pedido"])
    exigir_abierto(pedido)
    producto = estado["producto"]
    if producto is None:
        raise NoEncontrado("Producto no encontrado", codigo="PRODUCTO_NO_ENCONTRADO")
    if not producto.activo:
        raise Validacion("Producto no disponible", codigo="PRODUCTO_NO_DISPONIBLE")
    modificador = None
    if modificador_id:
        modificador = producto.modificador(modificador_id)
        if modificador is None:
            raise Validacion("Modificador no válido para este producto", codigo="MODIFICADOR_INVALIDO")
    if pedido.n_items >= MAX_LINEAS_PEDIDO:
        raise Validacion(f"El pedido alcanzó el máximo de {MAX_LINEAS_PEDIDO} líneas",
                         codigo="PEDIDO_DEMASIADO_GRANDE")
    item_id = id_propuesto(cuerpo, "item_id", ctx)
    if pedido.item(item_id) is not None:
        raise Conflicto("Ese identificador de ítem ya está en uso", codigo="ITEM_ID_EN_USO")

    item = Item(
        item_id=item_id, producto_id=producto.producto_id, nombre=producto.nombre,
        categoria=producto.categoria, cuarto_id=producto.cuarto_id, cantidad=cantidad,
        # Precio congelado al agregar: no cambia si el catálogo cambia después (igual que el local).
        precio_unitario=producto.precio + (modificador.precio_adicional if modificador else 0),
        creado_en=ctx.ahora_iso, modificador_id=modificador.modificador_id if modificador else None,
        modificador_nombre=modificador.nombre if modificador else None, observacion=observacion,
    )
    pedido.total += item.subtotal
    pedido.n_items += 1
    return Resultado(
        vistas.item(item), http=201,
        cambios=[item_cambio(ctx, pedido.pedido_id, item, nuevo=True), guardar_pedido(ctx, pedido)],
        eventos=[Evento("item.agregado", {"pedido_id": pedido.pedido_id, "mesa_id": pedido.mesa_id,
                                          "item": _datos_item(item)})],
    )


# --- modificar y quitar ítem --------------------------------------------------------------------------

def leer_pedido(almacen, ctx, cuerpo):
    return {"pedido": almacen.pedido(ctx.L, v.identificador(v.objeto(cuerpo), "pedido_id"))}


def ver_pedido(estado) -> dict:
    return vistas.pedido(exigir_pedido(estado["pedido"]))


def leer_pedido_e_item(almacen, ctx, cuerpo):
    datos = v.objeto(cuerpo)
    pedido_id = v.identificador(datos, "pedido_id")
    v.identificador(datos, "item_id")
    return {"pedido": almacen.pedido(ctx.L, pedido_id)}


def decidir_modificar(estado, ctx, cuerpo) -> Resultado:
    cantidad = v.entero(cuerpo, "cantidad", requerido=False, minimo=1, maximo=MAX_CANTIDAD)
    cambia_observacion = "observacion" in cuerpo
    observacion = v.texto(cuerpo, "observacion", requerido=False, max_largo=MAX_OBSERVACION)
    if cantidad is None and not cambia_observacion:
        raise Validacion("No hay campos para actualizar", codigo="SIN_CAMBIOS")

    pedido = exigir_pedido(estado["pedido"])
    exigir_abierto(pedido)
    item = exigir_item(pedido, cuerpo["item_id"])
    exigir_en_espera(item)

    if cantidad is not None:
        pedido.total += item.precio_unitario * (cantidad - item.cantidad)
        item.cantidad = cantidad
    if cambia_observacion:
        item.observacion = observacion
    return Resultado(
        vistas.item(item),
        cambios=[item_cambio(ctx, pedido.pedido_id, item, nuevo=False), guardar_pedido(ctx, pedido)],
        eventos=[Evento("item.modificado", {"pedido_id": pedido.pedido_id, "item": _datos_item(item)})],
    )


def decidir_quitar(estado, ctx, cuerpo) -> Resultado:
    pedido = exigir_pedido(estado["pedido"])
    exigir_abierto(pedido)
    item = exigir_item(pedido, cuerpo["item_id"])
    exigir_en_espera(item)

    pedido.total -= item.subtotal
    pedido.n_items -= 1
    pedido.items = [i for i in pedido.items if i.item_id != item.item_id]
    return Resultado(
        {"pedido_id": pedido.pedido_id, "item_id": item.item_id, "eliminado": True},
        cambios=[Borrar(tabla=OP, pk=claves.pedido(ctx.L, pedido.pedido_id), sk=claves.sk_item(item.item_id)),
                 guardar_pedido(ctx, pedido)],
        eventos=[Evento("item.quitado", {"pedido_id": pedido.pedido_id, "item": _datos_item(item)})],
    )


# --- enviar tanda ---------------------------------------------------------------------------------------

def leer_enviar(almacen, ctx, cuerpo):
    pedido_id = v.identificador(v.objeto(cuerpo), "pedido_id")
    pedido = almacen.pedido(ctx.L, pedido_id)
    return {
        "pedido": pedido,
        "mesa": almacen.mesa_estructura(ctx.L, pedido.mesa_id) if pedido else None,
        "cuartos": almacen.cuartos(ctx.L),
        "impresoras": almacen.impresoras(ctx.L),
    }


def decidir_enviar(estado, ctx, cuerpo) -> Resultado:
    pedido = exigir_pedido(estado["pedido"])
    exigir_abierto(pedido)
    pendientes = sorted((i for i in pedido.items if i.estado == "en_espera"), key=lambda i: i.item_id)
    if not pendientes:
        # Igual que el local: sin ítems en espera no es un error; no se escribe nada.
        return Resultado({"tanda": None, "items": _vista_items(pedido), "impresion": []})
    if len(pendientes) > MAX_LINEAS_TANDA:
        raise Validacion(f"Envía la comanda en partes: máximo {MAX_LINEAS_TANDA} líneas por tanda",
                         codigo="TANDA_DEMASIADO_GRANDE")

    tanda = pedido.n_tandas + 1
    pedido.n_tandas = tanda
    for item in pendientes:
        item.estado, item.tanda, item.enviado_en = "enviado", tanda, ctx.ahora_iso

    mesa = estado["mesa"]
    por_cuarto: OrderedDict[str, list[Item]] = OrderedDict()
    for item in pendientes:
        por_cuarto.setdefault(item.cuarto_id, []).append(item)

    cambios = [guardar_pedido(ctx, pedido)] + [item_cambio(ctx, pedido.pedido_id, i, nuevo=False) for i in pendientes]
    impresion = []
    for cuarto_id, items in por_cuarto.items():
        cuarto = estado["cuartos"].get(cuarto_id)
        impresora = estado["impresoras"].get(cuarto.impresora_id) if cuarto and cuarto.activo and cuarto.impresora_id else None
        nombre_cuarto = cuarto.nombre if cuarto else cuarto_id
        if impresora is None or not impresora.activa:
            impresion.append({"cuarto_id": cuarto_id, "cuarto": nombre_cuarto, "estado": "sin_impresora"})
            continue
        trabajo_id = ctx.nuevo_id()
        trabajo = {
            "tipo_item": "TRABAJO_IMPRESION", "trabajo_id": trabajo_id, "tipo": "comanda",
            "impresora_id": impresora.impresora_id, "pedido_id": pedido.pedido_id, "tanda": tanda,
            "mesa_id": pedido.mesa_id, "mesa_numero": mesa.numero if mesa else None,
            "sector": mesa.sector_nombre if mesa else None, "cuarto": nombre_cuarto,
            "garzon": ctx.usuario_nombre or ctx.usuario_id, "creado_en": ctx.ahora_iso, "origen": ctx.origen,
            "lineas": [{"cantidad": i.cantidad, "nombre": i.nombre, "modificador": i.modificador_nombre,
                        "observacion": i.observacion} for i in items],
        }
        if ctx.origen == "contingencia":
            # Al drenar la contingencia, la caja decide si imprimir: puede que ya se atendió en papel.
            trabajo["estado"] = "retenido_contingencia"
            cambios.append(Crear(tabla=OP, pk=claves.retenidos(ctx.L), sk=claves.sk_retenido(trabajo_id),
                                 atributos=trabajo))
            impresion.append({"cuarto_id": cuarto_id, "cuarto": nombre_cuarto, "estado": "retenida_contingencia"})
        else:
            trabajo.update({"estado": "pendiente", "GSI1PK": claves.VIGILAR_IMPRESION,
                            "GSI1SK": f"{ctx.ahora_iso}#{trabajo_id}"})
            cambios.append(Crear(tabla=OP, pk=claves.impresora(ctx.L, impresora.impresora_id),
                                 sk=claves.sk_trabajo_pendiente(trabajo_id), atributos=trabajo))
            impresion.append({"cuarto_id": cuarto_id, "cuarto": nombre_cuarto, "estado": "encolada"})

    return Resultado(
        {"tanda": tanda, "items": _vista_items(pedido), "impresion": impresion},
        cambios=cambios,
        eventos=[Evento("tanda.enviada", {"pedido_id": pedido.pedido_id, "mesa_id": pedido.mesa_id, "tanda": tanda,
                                          "items": [_datos_item(i) for i in pendientes], "impresion": impresion})],
    )


# --- precuenta y reapertura --------------------------------------------------------------------------

def leer_pedido_y_mesa(almacen, ctx, cuerpo):
    pedido_id = v.identificador(v.objeto(cuerpo), "pedido_id")
    pedido = almacen.pedido(ctx.L, pedido_id)
    return {"pedido": pedido, "mesa": almacen.mesa_estado(ctx.L, pedido.mesa_id) if pedido else None}


def _mesa_del_pedido(estado, pedido: Pedido) -> MesaEstado:
    mesa = estado["mesa"]
    if mesa is None or mesa.pedido_id != pedido.pedido_id:
        raise Conflicto("La mesa no corresponde a este pedido", codigo="MESA_INCONSISTENTE")
    return mesa


def decidir_precuenta(estado, ctx, cuerpo) -> Resultado:
    pedido = exigir_pedido(estado["pedido"])
    en_espera = sum(1 for i in pedido.items if i.estado == "en_espera")
    if pedido.estado == "precuenta":
        return Resultado({"pedido": vistas.pedido(pedido), "items_en_espera": en_espera})
    if pedido.estado == "cerrado":
        raise Conflicto("El pedido ya está cerrado", codigo="PEDIDO_CERRADO")
    if pedido.n_items == 0:
        raise Validacion("La mesa no tiene consumo", codigo="PEDIDO_VACIO")
    mesa = _mesa_del_pedido(estado, pedido)

    pedido.estado, mesa.estado = "precuenta", "precuenta"
    return Resultado(
        # items_en_espera avisa a la interfaz si hay consumo que nunca se envió a cocina.
        {"pedido": vistas.pedido(pedido), "mesa": vistas.mesa(mesa), "items_en_espera": en_espera},
        cambios=[guardar_pedido(ctx, pedido), guardar_mesa(ctx, mesa, pedido_esperado=pedido.pedido_id)],
        eventos=[Evento("precuenta.emitida", {"pedido_id": pedido.pedido_id, "mesa_id": pedido.mesa_id,
                                              "total": pedido.total})],
    )


def decidir_reabrir(estado, ctx, cuerpo) -> Resultado:
    confirmado = v.booleano(cuerpo, "confirmado")
    pedido = exigir_pedido(estado["pedido"])
    if pedido.estado == "abierto":
        return Resultado({"pedido": vistas.pedido(pedido)})
    if pedido.estado == "cerrado":
        raise Conflicto("El pedido ya está cerrado", codigo="PEDIDO_CERRADO")
    if not confirmado:
        raise Validacion("Reabrir la mesa deja sin efecto la precuenta. Confirma para continuar.",
                         codigo="CONFIRMACION_REQUERIDA")
    mesa = _mesa_del_pedido(estado, pedido)

    pedido.estado, mesa.estado = "abierto", "ocupada"
    return Resultado(
        {"pedido": vistas.pedido(pedido), "mesa": vistas.mesa(mesa)},
        cambios=[guardar_pedido(ctx, pedido), guardar_mesa(ctx, mesa, pedido_esperado=pedido.pedido_id)],
        eventos=[Evento("pedido.reabierto", {"pedido_id": pedido.pedido_id, "mesa_id": pedido.mesa_id,
                                             "con_pagos": pedido.pagado > 0, "pagado": pedido.pagado})],
    )


ABRIR = Operacion("pedido.abrir", "pedido.escribir", leer_abrir, decidir_abrir)
AGREGAR_ITEM = Operacion("pedido.agregar_item", "pedido.escribir", leer_agregar, decidir_agregar)
MODIFICAR_ITEM = Operacion("pedido.modificar_item", "pedido.escribir", leer_pedido_e_item, decidir_modificar)
QUITAR_ITEM = Operacion("pedido.quitar_item", "pedido.escribir", leer_pedido_e_item, decidir_quitar)
ENVIAR_TANDA = Operacion("pedido.enviar_tanda", "pedido.escribir", leer_enviar, decidir_enviar)
PRECUENTA = Operacion("pedido.precuenta", "pedido.escribir", leer_pedido_y_mesa, decidir_precuenta)
REABRIR = Operacion("pedido.reabrir", "pedido.escribir", leer_pedido_y_mesa, decidir_reabrir)

# Operaciones que pueden entrar por contingencia (la comanda). drenador-contingencia solo reaplica estas.
CONTINGENCIA = {op.nombre: op for op in (ABRIR, AGREGAR_ITEM, MODIFICAR_ITEM, QUITAR_ITEM, ENVIAR_TANDA, PRECUENTA, REABRIR)}
