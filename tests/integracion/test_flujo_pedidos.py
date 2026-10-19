"""Salón y comanda contra DynamoDB (moto): ejecutor + operaciones + adaptador."""

import pytest

from pos_dominio import claves
from pos_dominio.ejecutor import ejecutar
from pos_dominio.errores import Conflicto, NoEncontrado, Prohibido, Validacion
from pos_dominio.operaciones import pedidos as P

from integracion.semilla import L, contar, ctx, sembrar


@pytest.fixture
def local(dynamo, almacen):
    sembrar(dynamo)
    return almacen


def abrir(almacen, mesa="m1", usuario="garzon1"):
    return ejecutar(almacen, P.ABRIR, ctx(usuario), {"mesa_id": mesa})


def agregar(almacen, pedido_id, producto="pizza", **extra):
    return ejecutar(almacen, P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, "producto_id": producto, **extra})


def enviar(almacen, pedido_id, **ctx_extra):
    return ejecutar(almacen, P.ENVIAR_TANDA, ctx(**ctx_extra), {"pedido_id": pedido_id})


class TestAbrir:
    def test_crea_pedido_y_ocupa_la_mesa(self, local):
        r = abrir(local)
        assert r.http == 201 and r.cuerpo["estado"] == "abierto"
        mesa = local.mesa_estado(L, "m1")
        assert (mesa.estado, mesa.pedido_id, mesa.garzon_id) == ("ocupada", r.cuerpo["pedido_id"], "garzon1")

    def test_segunda_apertura_devuelve_el_mismo_pedido_sin_escribir(self, local, dynamo):
        primero = abrir(local)
        segundo = abrir(local, usuario="garzon2")
        assert segundo.http == 200 and segundo.cuerpo["pedido_id"] == primero.cuerpo["pedido_id"]
        assert contar(dynamo, "operacion", claves.eventos(L)) == 1

    def test_mesa_inexistente(self, local):
        with pytest.raises(NoEncontrado):
            abrir(local, mesa="no_existe")

    def test_D5_mesa_bloqueada_no_recibe_pedido(self, local, dynamo):
        dynamo.put_item(TableName="operacion", Item={"PK": {"S": claves.salon(L)}, "SK": {"S": "MESA#m2"},
                                                     "mesa_id": {"S": "m2"}, "estado": {"S": "bloqueada"},
                                                     "version": {"N": "1"}})
        with pytest.raises(Conflicto) as error:
            abrir(local, mesa="m2")
        assert error.value.codigo == "MESA_BLOQUEADA"

    def test_cocina_no_puede_abrir_mesas(self, local):
        with pytest.raises(Prohibido):
            ejecutar(local, P.ABRIR, ctx("cocina1", "cocina"), {"mesa_id": "m1"})


class TestComanda:
    def test_precio_congelado_y_total_del_pedido(self, local):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        item = agregar(local, pedido_id, cantidad=2, modificador_id="xl", observacion=" sin cebolla ").cuerpo
        assert (item["precio_unitario"], item["subtotal"], item["observacion"]) == (10000, 20000, "sin cebolla")
        assert local.pedido(L, pedido_id).total == 20000

    @pytest.mark.parametrize("extra,codigo", [
        ({"producto_id": "agotado"}, "PRODUCTO_NO_DISPONIBLE"),
        ({"modificador_id": "no_existe"}, "MODIFICADOR_INVALIDO"),
        ({"cantidad": 0}, "CAMPO_INVALIDO"),
        ({"cantidad": True}, "CAMPO_INVALIDO"),
        ({"observacion": "x" * 501}, "CAMPO_INVALIDO"),
    ])
    def test_validaciones_al_agregar(self, local, extra, codigo):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        cuerpo = {"producto_id": "pizza", **extra}
        with pytest.raises(Validacion) as error:
            ejecutar(local, P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, **cuerpo})
        assert error.value.codigo == codigo

    def test_tandas_envian_solo_lo_que_espera_y_crean_un_trabajo_por_impresora(self, local, dynamo):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        agregar(local, pedido_id, "pizza")
        agregar(local, pedido_id, "bebida")
        r = enviar(local, pedido_id).cuerpo
        assert r["tanda"] == 1
        assert {i["estado"] for i in r["items"]} == {"enviado"}
        # cocina tiene impresora; la barra no
        assert sorted((x["cuarto_id"], x["estado"]) for x in r["impresion"]) == [
            ("barra", "sin_impresora"), ("cocina", "encolada")]
        assert contar(dynamo, "operacion", claves.impresora(L, "imp_cocina"), "PEND#") == 1

        agregar(local, pedido_id, "pizza", cantidad=3)
        r = enviar(local, pedido_id).cuerpo
        assert r["tanda"] == 2
        assert sorted(i["tanda"] for i in r["items"]) == [1, 1, 2]
        assert contar(dynamo, "operacion", claves.impresora(L, "imp_cocina"), "PEND#") == 2

    def test_enviar_sin_items_en_espera_no_escribe(self, local, dynamo):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        antes = contar(dynamo, "operacion", claves.eventos(L))
        assert enviar(local, pedido_id).cuerpo["tanda"] is None
        assert contar(dynamo, "operacion", claves.eventos(L)) == antes

    def test_en_contingencia_la_impresion_queda_retenida(self, local, dynamo):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        agregar(local, pedido_id, "pizza")
        r = enviar(local, pedido_id, origen="contingencia").cuerpo
        assert r["impresion"] == [{"cuarto_id": "cocina", "cuarto": "Cocina", "estado": "retenida_contingencia"}]
        assert contar(dynamo, "operacion", claves.retenidos(L)) == 1
        assert contar(dynamo, "operacion", claves.impresora(L, "imp_cocina")) == 0

    def test_D3_un_item_enviado_no_se_modifica_ni_se_quita(self, local):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        item_id = agregar(local, pedido_id).cuerpo["item_id"]
        enviar(local, pedido_id)
        for op, cuerpo in ((P.MODIFICAR_ITEM, {"cantidad": 1}), (P.QUITAR_ITEM, {})):
            with pytest.raises(Conflicto) as error:
                ejecutar(local, op, ctx(), {"pedido_id": pedido_id, "item_id": item_id, **cuerpo})
            assert error.value.codigo == "ITEM_YA_ENVIADO"

    def test_modificar_y_quitar_un_item_en_espera_ajusta_el_total(self, local):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        item_id = agregar(local, pedido_id, "bebida").cuerpo["item_id"]
        ejecutar(local, P.MODIFICAR_ITEM, ctx(), {"pedido_id": pedido_id, "item_id": item_id, "cantidad": 4})
        assert local.pedido(L, pedido_id).total == 6000
        ejecutar(local, P.QUITAR_ITEM, ctx(), {"pedido_id": pedido_id, "item_id": item_id})
        pedido = local.pedido(L, pedido_id)
        assert (pedido.total, pedido.n_items, pedido.items) == (0, 0, [])


class TestPrecuentaYReapertura:
    def preparar(self, local):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        agregar(local, pedido_id)
        ejecutar(local, P.PRECUENTA, ctx(), {"pedido_id": pedido_id})
        return pedido_id

    def test_precuenta_marca_pedido_y_mesa(self, local):
        pedido_id = self.preparar(local)
        assert local.pedido(L, pedido_id).estado == "precuenta"
        assert local.mesa_estado(L, "m1").estado == "precuenta"

    def test_precuenta_de_pedido_vacio_se_rechaza(self, local):
        pedido_id = abrir(local).cuerpo["pedido_id"]
        with pytest.raises(Validacion) as error:
            ejecutar(local, P.PRECUENTA, ctx(), {"pedido_id": pedido_id})
        assert error.value.codigo == "PEDIDO_VACIO"

    def test_D1_M13_en_precuenta_no_se_agrega_sin_reabrir(self, local):
        pedido_id = self.preparar(local)
        with pytest.raises(Conflicto) as error:
            agregar(local, pedido_id, "bebida")
        assert error.value.codigo == "PEDIDO_EN_PRECUENTA"

    def test_M13_reabrir_exige_confirmacion_del_garzon(self, local):
        pedido_id = self.preparar(local)
        with pytest.raises(Validacion) as error:
            ejecutar(local, P.REABRIR, ctx(), {"pedido_id": pedido_id})
        assert error.value.codigo == "CONFIRMACION_REQUERIDA"
        r = ejecutar(local, P.REABRIR, ctx(), {"pedido_id": pedido_id, "confirmado": True})
        assert r.cuerpo["pedido"]["estado"] == "abierto"
        assert local.mesa_estado(L, "m1").estado == "ocupada"
        assert agregar(local, pedido_id, "bebida").http == 201
