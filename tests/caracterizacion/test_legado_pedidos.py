"""Caracterización de pedidos y comandas en el POS local (copia congelada en legado/).

Estas pruebas describen lo que el sistema hace HOY, incluidos los defectos. Los defectos se marcan
con su código del inventario (D1, D2...). La versión nueva los corrige; ver
tests/dominio/test_pedidos.py y docs/migracion/caracterizacion.md.
"""

import pytest

from app.application.use_cases.pedidos_use_cases import (
    ActualizarItemUseCase,
    AgregarItemUseCase,
    EliminarItemUseCase,
    EnviarTandaUseCase,
    FinalizarCuentaUseCase,
    GenerarPrecuentaUseCase,
    ObtenerOCrearPedidoUseCase,
)
from app.domain.entities import ItemCobrado
from app.domain.exceptions import NotFoundError, ValidationError

from caracterizacion.dobles import MesasEnMemoria, PagosEnMemoria, PedidosEnMemoria, ProductosEnMemoria


@pytest.fixture
def pos():
    class Pos:
        pass

    p = Pos()
    p.mesas = MesasEnMemoria()
    p.productos = ProductosEnMemoria()
    p.pedidos = PedidosEnMemoria(p.productos)
    p.pagos = PagosEnMemoria()
    p.mesas.agregar("m1")
    p.productos.agregar("pizza", 8000, modificadores=[("mod_xl", "XL", 2000)])
    p.productos.agregar("bebida", 1500)
    p.productos.agregar("agotado", 3000, activo=False)
    p.productos.agregar("otro", 1000, modificadores=[("mod_otro", "Otro", 500)])
    return p


def abrir(pos, mesa="m1", garzon="g1"):
    return ObtenerOCrearPedidoUseCase(pos.pedidos, pos.mesas).execute(mesa, garzon)


def agregar(pos, pedido_id, producto, cantidad=1, modificador=None, obs=None):
    return AgregarItemUseCase(pos.pedidos, pos.productos).execute(pedido_id, producto, cantidad, modificador, obs)


class TestAbrirPedido:
    def test_crea_pedido_abierto_y_ocupa_la_mesa_con_el_garzon(self, pos):
        pedido = abrir(pos)
        assert pedido.estado == "abierto"
        assert pos.mesas.mesas["m1"].estado == "ocupada"
        assert pos.mesas.mesas["m1"].garzon_asignado_id == "g1"

    def test_segunda_llamada_devuelve_el_mismo_pedido(self, pos):
        assert abrir(pos).pedido_id == abrir(pos, garzon="g2").pedido_id

    def test_conserva_el_garzon_ya_asignado_a_la_mesa(self, pos):
        pos.mesas.agregar("m2", garzon="g_asignado")
        abrir(pos, mesa="m2", garzon="g1")
        assert pos.mesas.mesas["m2"].garzon_asignado_id == "g_asignado"

    def test_mesa_inexistente(self, pos):
        with pytest.raises(NotFoundError):
            abrir(pos, mesa="no_existe")

    def test_D5_mesa_bloqueada_recibe_pedido_y_sigue_bloqueada(self, pos):
        pos.mesas.agregar("m3", estado="bloqueada")
        pedido = abrir(pos, mesa="m3")
        assert pedido.estado == "abierto"
        assert pos.mesas.mesas["m3"].estado == "bloqueada"


class TestAgregarItem:
    def test_precio_congelado_es_precio_mas_recargo(self, pos):
        pedido = abrir(pos)
        item = agregar(pos, pedido.pedido_id, "pizza", 2, "mod_xl", "sin cebolla")
        assert item.precio_unitario == 10000
        assert item.cantidad == 2
        assert item.estado == "en_espera"
        assert item.observacion_libre == "sin cebolla"

    def test_cambio_de_precio_posterior_no_afecta_al_item(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "bebida")
        pos.productos.productos["bebida"].precio = 9999
        assert pos.pedidos.find_by_id(pedido.pedido_id).items[0].precio_unitario == 1500

    @pytest.mark.parametrize("cantidad", [0, -1])
    def test_cantidad_debe_ser_positiva(self, pos, cantidad):
        with pytest.raises(ValidationError, match="cantidad debe ser mayor a 0"):
            agregar(pos, abrir(pos).pedido_id, "bebida", cantidad)

    def test_producto_inactivo(self, pos):
        with pytest.raises(ValidationError, match="Producto no disponible"):
            agregar(pos, abrir(pos).pedido_id, "agotado")

    def test_modificador_de_otro_producto(self, pos):
        with pytest.raises(ValidationError, match="Modificador no válido"):
            agregar(pos, abrir(pos).pedido_id, "pizza", 1, "mod_otro")

    def test_D1_se_puede_agregar_a_un_pedido_cerrado(self, pos):
        pedido = abrir(pos)
        pos.pedidos.cerrar(pedido.pedido_id)
        assert agregar(pos, pedido.pedido_id, "bebida").estado == "en_espera"

    def test_D1_se_puede_agregar_a_un_pedido_en_precuenta(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "bebida")
        GenerarPrecuentaUseCase(pos.pedidos, pos.mesas).execute(pedido.pedido_id)
        assert agregar(pos, pedido.pedido_id, "pizza").estado == "en_espera"
        assert pos.pedidos.pedidos[pedido.pedido_id].estado == "precuenta"


class TestTandasYEspera:
    def test_comanda_por_tandas_envia_solo_lo_que_espera(self, pos):
        pedido = abrir(pos)
        primeros = [agregar(pos, pedido.pedido_id, "pizza"), agregar(pos, pedido.pedido_id, "bebida")]
        items = EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id)
        assert [i.estado for i in items] == ["enviado", "enviado"]

        segundo = agregar(pos, pedido.pedido_id, "bebida", 3)
        assert segundo.estado == "en_espera"
        items = EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id)
        assert {i.item_id: i.estado for i in items} == {
            primeros[0].item_id: "enviado", primeros[1].item_id: "enviado", segundo.item_id: "enviado"}

    def test_enviar_sin_items_en_espera_no_falla_y_devuelve_todos(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "pizza")
        EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id)
        assert len(EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id)) == 1

    def test_no_se_puede_retener_un_item_y_enviar_otro(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "pizza")
        agregar(pos, pedido.pedido_id, "bebida")
        assert all(i.estado == "enviado" for i in EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id))

    def test_se_quita_un_item_en_espera(self, pos):
        pedido = abrir(pos)
        item = agregar(pos, pedido.pedido_id, "pizza")
        EliminarItemUseCase(pos.pedidos).execute(pedido.pedido_id, item.item_id)
        assert pos.pedidos.find_by_id(pedido.pedido_id).items == []

    def test_no_se_quita_un_item_enviado_y_responde_no_encontrado(self, pos):
        pedido = abrir(pos)
        item = agregar(pos, pedido.pedido_id, "pizza")
        EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id)
        with pytest.raises(NotFoundError, match="ya fue enviado"):
            EliminarItemUseCase(pos.pedidos).execute(pedido.pedido_id, item.item_id)

    def test_D3_se_puede_bajar_la_cantidad_de_un_item_enviado(self, pos):
        pedido = abrir(pos)
        item = agregar(pos, pedido.pedido_id, "pizza", 3)
        EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id)
        actualizado = ActualizarItemUseCase(pos.pedidos).execute(pedido.pedido_id, item.item_id, 1, None,
                                                                  None, False)
        assert actualizado.cantidad == 1

    def test_D3_un_item_enviado_puede_volver_a_espera_y_quitarse(self, pos):
        pedido = abrir(pos)
        item = agregar(pos, pedido.pedido_id, "pizza")
        EnviarTandaUseCase(pos.pedidos).execute(pedido.pedido_id)
        ActualizarItemUseCase(pos.pedidos).execute(pedido.pedido_id, item.item_id, None, "en_espera", None,
                                                   False)
        EliminarItemUseCase(pos.pedidos).execute(pedido.pedido_id, item.item_id)
        assert pos.pedidos.find_by_id(pedido.pedido_id).items == []

    def test_actualizar_sin_campos(self, pos):
        pedido = abrir(pos)
        item = agregar(pos, pedido.pedido_id, "pizza")
        with pytest.raises(ValidationError, match="No hay campos para actualizar"):
            ActualizarItemUseCase(pos.pedidos).execute(pedido.pedido_id, item.item_id, None, None, None, False)


class TestPrecuentaYFinalizar:
    def test_precuenta_marca_pedido_y_mesa(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "pizza")
        mesa = GenerarPrecuentaUseCase(pos.pedidos, pos.mesas).execute(pedido.pedido_id)
        assert mesa.estado == "precuenta"
        assert pos.pedidos.pedidos[pedido.pedido_id].estado == "precuenta"

    def test_D2_precuenta_reabre_un_pedido_cerrado(self, pos):
        pedido = abrir(pos)
        pos.pedidos.cerrar(pedido.pedido_id)
        GenerarPrecuentaUseCase(pos.pedidos, pos.mesas).execute(pedido.pedido_id)
        assert pos.pedidos.pedidos[pedido.pedido_id].estado == "precuenta"

    def test_precuenta_de_pedido_vacio_se_permite(self, pos):
        pedido = abrir(pos)
        assert GenerarPrecuentaUseCase(pos.pedidos, pos.mesas).execute(pedido.pedido_id).estado == "precuenta"

    def test_finalizar_con_saldo_pendiente_falla(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "pizza")
        with pytest.raises(ValidationError, match="saldo pendiente"):
            FinalizarCuentaUseCase(pos.pedidos, pos.mesas, pos.pagos).execute(pedido.pedido_id)

    def test_finalizar_pagado_cierra_y_libera_la_mesa(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "pizza")
        pos.pagos.create(pedido.pedido_id, "m1", "t", "efectivo", 8000, 800, None, None, None, None, None,
                         "completa", None, [])
        cerrado = FinalizarCuentaUseCase(pos.pedidos, pos.mesas, pos.pagos).execute(pedido.pedido_id)
        assert cerrado.estado == "cerrado"
        assert pos.mesas.mesas["m1"].estado == "libre"
        assert pos.mesas.mesas["m1"].garzon_asignado_id is None

    def test_finalizar_no_exige_precuenta(self, pos):
        pedido = abrir(pos)
        assert FinalizarCuentaUseCase(pos.pedidos, pos.mesas, pos.pagos).execute(pedido.pedido_id).estado \
            == "cerrado"

    def test_la_propina_no_cuenta_para_cubrir_el_total(self, pos):
        pedido = abrir(pos)
        agregar(pos, pedido.pedido_id, "pizza")
        pos.pagos.create(pedido.pedido_id, "m1", "t", "efectivo", 7000, 1000, None, None, None, None, None,
                         "completa", None, [ItemCobrado("x", 1)])
        with pytest.raises(ValidationError):
            FinalizarCuentaUseCase(pos.pedidos, pos.mesas, pos.pagos).execute(pedido.pedido_id)
