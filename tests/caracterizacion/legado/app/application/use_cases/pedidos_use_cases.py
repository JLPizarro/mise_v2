from app.application.ports import (
    MesaRepository,
    PagoRepository,
    PedidoRepository,
    ProductoRepository,
)
from app.domain.entities import ItemComanda, Pedido
from app.domain.exceptions import NotFoundError, ValidationError

ESTADOS_ITEM_VALIDOS = {"en_espera", "enviado"}


class ObtenerOCrearPedidoUseCase:
    """Devuelve el pedido abierto/precuenta de una mesa, o crea uno nuevo y ocupa la mesa."""

    def __init__(
        self,
        pedidos: PedidoRepository,
        mesas: MesaRepository,
    ):
        self._pedidos = pedidos
        self._mesas = mesas

    def execute(self, mesa_id: str, garzon_id: str) -> Pedido:
        if self._mesas.find_by_id(mesa_id) is None:
            raise NotFoundError("Mesa no encontrada")

        pedido = self._pedidos.find_abierto_by_mesa(mesa_id)

        if pedido is not None:
            return pedido

        pedido = self._pedidos.create(mesa_id, garzon_id)
        self._mesas.ocupar_si_libre(mesa_id, garzon_id)

        return pedido


class ObtenerPedidoUseCase:
    def __init__(self, pedidos: PedidoRepository):
        self._pedidos = pedidos

    def execute(self, pedido_id: str) -> Pedido:
        pedido = self._pedidos.find_by_id(pedido_id)

        if pedido is None:
            raise NotFoundError("Pedido no encontrado")

        return pedido


class ListarPedidosUseCase:
    def __init__(self, pedidos: PedidoRepository):
        self._pedidos = pedidos

    def execute(self, mesa_id: str | None, estado: str | None) -> list[Pedido]:
        return self._pedidos.list_by_filters(mesa_id, estado)


class AgregarItemUseCase:
    def __init__(self, pedidos: PedidoRepository, productos: ProductoRepository):
        self._pedidos = pedidos
        self._productos = productos

    def execute(
        self,
        pedido_id: str,
        producto_id: str,
        cantidad: int,
        modificador_id: str | None,
        observacion_libre: str | None,
    ) -> ItemComanda:
        if cantidad <= 0:
            raise ValidationError("cantidad debe ser mayor a 0")

        if self._pedidos.find_by_id(pedido_id) is None:
            raise NotFoundError("Pedido no encontrado")

        producto = self._productos.find_by_id(producto_id)

        if producto is None:
            raise NotFoundError("Producto no encontrado")

        if not producto.activo:
            raise ValidationError("Producto no disponible")

        precio_adicional = 0

        if modificador_id:
            modificador = self._productos.find_modificador(modificador_id, producto_id)

            if modificador is None:
                raise ValidationError("Modificador no válido para este producto")

            precio_adicional = modificador.precio_adicional

        precio_unitario = producto.precio + precio_adicional

        return self._pedidos.add_item(
            pedido_id,
            producto_id,
            modificador_id,
            cantidad,
            observacion_libre,
            precio_unitario,
        )


class ActualizarItemUseCase:
    def __init__(self, pedidos: PedidoRepository):
        self._pedidos = pedidos

    def execute(
        self,
        pedido_id: str,
        item_id: str,
        cantidad: int | None,
        estado: str | None,
        observacion_libre: str | None,
        set_observacion: bool,
    ) -> ItemComanda:
        if cantidad is not None and cantidad <= 0:
            raise ValidationError("cantidad debe ser mayor a 0")

        if estado is not None and estado not in ESTADOS_ITEM_VALIDOS:
            raise ValidationError("estado inválido")

        if cantidad is None and estado is None and not set_observacion:
            raise ValidationError("No hay campos para actualizar")

        item = self._pedidos.update_item(
            pedido_id,
            item_id,
            cantidad=cantidad,
            estado=estado,
            observacion_libre=observacion_libre,
            set_observacion=set_observacion,
        )

        if item is None:
            raise NotFoundError("Item no encontrado")

        return item


class EliminarItemUseCase:
    def __init__(self, pedidos: PedidoRepository):
        self._pedidos = pedidos

    def execute(self, pedido_id: str, item_id: str) -> None:
        eliminado = self._pedidos.delete_item_en_espera(pedido_id, item_id)

        if not eliminado:
            raise NotFoundError("Item no encontrado o ya fue enviado")


class EnviarTandaUseCase:
    def __init__(self, pedidos: PedidoRepository):
        self._pedidos = pedidos

    def execute(self, pedido_id: str) -> list[ItemComanda]:
        if self._pedidos.find_by_id(pedido_id) is None:
            raise NotFoundError("Pedido no encontrado")

        return self._pedidos.enviar_tanda(pedido_id)


class GenerarPrecuentaUseCase:
    def __init__(self, pedidos: PedidoRepository, mesas: MesaRepository):
        self._pedidos = pedidos
        self._mesas = mesas

    def execute(self, pedido_id: str):
        pedido = self._pedidos.marcar_precuenta(pedido_id)

        if pedido is None:
            raise NotFoundError("Pedido no encontrado")

        mesa = self._mesas.marcar_precuenta(pedido.mesa_id)

        if mesa is None:
            raise NotFoundError("Mesa no encontrada")

        return mesa


class FinalizarCuentaUseCase:
    """Cierra el pedido y libera la mesa una vez que la cuenta quedó
    completamente pagada. Se invoca explícitamente desde caja — normalmente
    después de emitir el documento tributario — y no como efecto automático
    de registrar un pago, para permitir cobros parciales/mixtos."""

    def __init__(
        self,
        pedidos: PedidoRepository,
        mesas: MesaRepository,
        pagos: PagoRepository,
    ):
        self._pedidos = pedidos
        self._mesas = mesas
        self._pagos = pagos

    def execute(self, pedido_id: str) -> Pedido:
        pedido = self._pedidos.find_by_id(pedido_id)

        if pedido is None:
            raise NotFoundError("Pedido no encontrado")

        total = sum(item.precio_unitario * item.cantidad for item in pedido.items)
        pagado = sum(p.monto for p in self._pagos.list_by_pedido(pedido_id))

        if pagado < total:
            raise ValidationError(
                "El pedido todavía tiene saldo pendiente, no se puede finalizar"
            )

        self._pedidos.cerrar(pedido_id)
        self._mesas.liberar(pedido.mesa_id)

        pedido.estado = "cerrado"

        return pedido
