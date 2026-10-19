"""Forma de las respuestas JSON. Solo enteros, textos, booleanos, listas y dicts."""

from pos_dominio.modelos import Item, MesaEstado, Pago, Pedido, Turno


def item(i: Item) -> dict:
    return {
        "item_id": i.item_id, "producto_id": i.producto_id, "nombre": i.nombre, "categoria": i.categoria,
        "cuarto_id": i.cuarto_id, "modificador_id": i.modificador_id, "modificador_nombre": i.modificador_nombre,
        "cantidad": i.cantidad, "cobrado": i.cobrado, "precio_unitario": i.precio_unitario,
        "subtotal": i.subtotal, "estado": i.estado, "tanda": i.tanda, "observacion": i.observacion,
        "creado_en": i.creado_en, "enviado_en": i.enviado_en,
    }


def pago(p: Pago) -> dict:
    return {
        "pago_id": p.pago_id, "turno_id": p.turno_id, "metodo": p.metodo, "monto": p.monto, "propina": p.propina,
        "tipo_division": p.tipo_division, "codigo_autorizacion_pos": p.codigo_autorizacion_pos,
        "efectivo_recibido": p.efectivo_recibido, "vuelto": p.vuelto, "items_cobrados": p.items_cobrados,
        "usuario_id": p.usuario_id, "fecha": p.fecha,
    }


def pedido(p: Pedido) -> dict:
    return {
        "pedido_id": p.pedido_id, "mesa_id": p.mesa_id, "garzon_id": p.garzon_id, "estado": p.estado,
        "total": p.total, "pagado": p.pagado, "saldo": p.saldo, "propina_total": p.propina_total,
        "n_tandas": p.n_tandas, "documento": p.documento, "creado_en": p.creado_en, "cerrado_en": p.cerrado_en,
        "items": [item(i) for i in sorted(p.items, key=lambda i: i.item_id)],
        "pagos": [pago(x) for x in sorted(p.pagos, key=lambda x: x.pago_id)],
    }


def mesa(m: MesaEstado) -> dict:
    return {"mesa_id": m.mesa_id, "estado": m.estado, "pedido_id": m.pedido_id, "garzon_id": m.garzon_id}


def turno(t: Turno) -> dict:
    """Arqueo ciego: mientras el turno está abierto no se exponen los totales, porque con ellos el
    cajero podría deducir el efectivo esperado antes de contar (caja_use_cases / CierreCaja.tsx)."""
    vista = {
        "turno_id": t.turno_id, "estado": t.estado, "monto_apertura": t.monto_apertura,
        "usuario_apertura_id": t.usuario_apertura_id, "abierto_en": t.abierto_en,
        "fecha_operativa": t.fecha_operativa, "primer_conteo": t.primer_conteo,
        "segundo_conteo": t.segundo_conteo, "requiere_segundo_conteo": t.requiere_segundo_conteo,
        "conciliacion": t.conciliacion, "usuario_cierre_id": t.usuario_cierre_id, "cerrado_en": t.cerrado_en,
    }
    if t.estado == "cerrado":
        vista["resultado"] = t.resultado
    return vista
