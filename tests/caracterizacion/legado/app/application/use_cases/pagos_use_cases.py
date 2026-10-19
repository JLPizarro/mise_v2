from app.application.ports import PagoRepository, PedidoRepository
from app.domain.entities import ItemCobrado, Pago
from app.domain.exceptions import NotFoundError, ValidationError

METODOS_VALIDOS = {"efectivo", "debito", "credito", "transferencia"}
TIPOS_DIVISION_VALIDOS = {"completa", "items", "partes_iguales", "monto_libre"}
TIPOS_DOCUMENTO_VALIDOS = {"boleta", "factura"}


def _calcular_total_pedido(pedido) -> int:
    return sum(item.precio_unitario * item.cantidad for item in pedido.items)


class RegistrarPagoUseCase:
    """Registra un cobro (posiblemente parcial) sobre un pedido.

    A propósito NO cierra el pedido ni libera la mesa: eso lo hace de forma
    explícita FinalizarCuentaUseCase una vez que la cuenta queda completamente
    pagada (después de emitir el documento tributario en la UI de caja).
    """

    def __init__(self, pagos: PagoRepository, pedidos: PedidoRepository):
        self._pagos = pagos
        self._pedidos = pedidos

    def execute(
        self,
        mesa_id: str,
        metodo: str,
        monto: int,
        propina: int,
        pedido_id: str | None,
        turno_id: str | None,
        codigo_autorizacion_pos: str | None,
        efectivo_recibido: int | None,
        vuelto: int | None,
        rut_facturacion: str | None,
        razon_social_facturacion: str | None,
        tipo_division: str | None,
        tipo_documento: str | None,
        items_cobrados: list[ItemCobrado] | None,
    ) -> Pago:
        if metodo not in METODOS_VALIDOS:
            raise ValidationError("metodo de pago inválido")

        if monto <= 0:
            raise ValidationError("monto debe ser mayor a 0")

        if metodo in ("debito", "credito") and not codigo_autorizacion_pos:
            raise ValidationError("codigo_autorizacion_pos es requerido para tarjetas")

        if tipo_division is not None and tipo_division not in TIPOS_DIVISION_VALIDOS:
            raise ValidationError("tipo_division inválido")

        if tipo_documento is not None and tipo_documento not in TIPOS_DOCUMENTO_VALIDOS:
            raise ValidationError("tipo_documento inválido")

        items_cobrados = items_cobrados or []

        if pedido_id:
            pedido = self._pedidos.find_by_id(pedido_id)

            if pedido is None:
                raise NotFoundError("Pedido no encontrado")

            total_pedido = _calcular_total_pedido(pedido)
            pagos_previos = self._pagos.list_by_pedido(pedido_id)
            ya_pagado = sum(p.monto for p in pagos_previos)
            saldo_pendiente = total_pedido - ya_pagado

            if monto > saldo_pendiente:
                raise ValidationError(
                    "El monto excede el saldo pendiente del pedido"
                )

            if items_cobrados:
                items_por_id = {item.item_id: item for item in pedido.items}

                pagadas_por_item: dict[str, int] = {}

                for pago_previo in pagos_previos:
                    for item_cobrado in pago_previo.items_cobrados:
                        pagadas_por_item[item_cobrado.item_id] = (
                            pagadas_por_item.get(item_cobrado.item_id, 0)
                            + item_cobrado.cantidad
                        )

                for item_cobrado in items_cobrados:
                    item = items_por_id.get(item_cobrado.item_id)

                    if item is None:
                        raise ValidationError(
                            "Uno de los ítems no pertenece a este pedido"
                        )

                    disponibles = item.cantidad - pagadas_por_item.get(
                        item_cobrado.item_id, 0
                    )

                    if item_cobrado.cantidad > disponibles:
                        raise ValidationError(
                            f"La cantidad cobrada de '{item.producto.nombre if item.producto else item.producto_id}' "
                            "excede lo disponible para ese ítem"
                        )

        return self._pagos.create(
            pedido_id,
            mesa_id,
            turno_id,
            metodo,
            monto,
            propina,
            codigo_autorizacion_pos,
            efectivo_recibido,
            vuelto,
            rut_facturacion,
            razon_social_facturacion,
            tipo_division,
            tipo_documento,
            items_cobrados,
        )
