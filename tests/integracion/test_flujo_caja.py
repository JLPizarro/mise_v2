"""Caja contra DynamoDB (moto): cobro, venta, turno, arqueo ciego y retiros con autorización."""

import pytest

from pos_dominio import autorizacion, claves
from pos_dominio.ejecutor import ejecutar
from pos_dominio.errores import Conflicto, Prohibido, Validacion
from pos_dominio.operaciones import caja as C
from pos_dominio.operaciones import pedidos as P

from integracion.semilla import CODIGO_ADMIN, L, contar, ctx, sembrar


def cajero(**extra):
    return ctx("cajero1", "cajero", **extra)


@pytest.fixture
def local(dynamo, almacen):
    sembrar(dynamo)
    return almacen


@pytest.fixture
def turno_id(local):
    return ejecutar(local, C.ABRIR_TURNO, cajero(), {"monto_apertura": 50_000}).cuerpo["turno_id"]


def pedido_con(local, *lineas, mesa="m1"):
    pedido_id = ejecutar(local, P.ABRIR, ctx(), {"mesa_id": mesa}).cuerpo["pedido_id"]
    items = [ejecutar(local, P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, "producto_id": prod, "cantidad": cant})
             .cuerpo["item_id"] for prod, cant in lineas]
    ejecutar(local, P.ENVIAR_TANDA, ctx(), {"pedido_id": pedido_id})
    ejecutar(local, P.PRECUENTA, ctx(), {"pedido_id": pedido_id})
    return pedido_id, items


def pagar(local, pedido_id, medios, **extra):
    return ejecutar(local, C.REGISTRAR_PAGO, cajero(), {"pedido_id": pedido_id, "medios": medios, **extra})


def efectivo(monto, propina=0, recibido=None):
    return {"metodo": "efectivo", "monto": monto, "propina": propina,
            "efectivo_recibido": monto + propina if recibido is None else recibido}


class TestPagos:
    def test_sin_turno_abierto_no_se_cobra(self, local):
        pedido_id, _ = pedido_con(local, ("pizza", 1))
        with pytest.raises(Conflicto) as error:
            pagar(local, pedido_id, [efectivo(8000)])
        assert error.value.codigo == "TURNO_NO_ABIERTO"

    def test_pago_mixto_es_un_solo_comando_y_acumula_en_el_turno(self, local, turno_id):
        pedido_id, _ = pedido_con(local, ("pizza", 1), ("bebida", 2))  # 11.000
        r = pagar(local, pedido_id, [{"metodo": "debito", "monto": 6000, "codigo_autorizacion_pos": "A1"},
                                     efectivo(5000, propina=1100, recibido=10_000)])
        assert r.http == 201
        assert [p["vuelto"] for p in r.cuerpo["pagos"]] == [None, 3900]
        assert r.cuerpo["pedido"]["saldo"] == 0
        turno = local.turno(L, turno_id)
        assert (turno.tot_debito, turno.tot_efectivo, turno.n_pagos) == (6000, 6100, 2)

    @pytest.mark.parametrize("medio,codigo", [
        ({"metodo": "cheque", "monto": 100}, "METODO_INVALIDO"),
        ({"metodo": "credito", "monto": 100}, "CODIGO_POS_REQUERIDO"),
        ({"metodo": "efectivo", "monto": 100, "propina": 10, "efectivo_recibido": 109}, "EFECTIVO_INSUFICIENTE"),
        ({"metodo": "efectivo", "monto": 100}, "CAMPO_INVALIDO"),
        ({"metodo": "transferencia", "monto": 100, "propina": -1}, "CAMPO_INVALIDO"),
    ])
    def test_validaciones_de_medio(self, local, turno_id, medio, codigo):
        pedido_id, _ = pedido_con(local, ("pizza", 1))
        with pytest.raises(Validacion) as error:
            pagar(local, pedido_id, [medio])
        assert error.value.codigo == codigo

    def test_mas_de_dos_medios_se_rechaza(self, local, turno_id):
        pedido_id, _ = pedido_con(local, ("pizza", 1))
        with pytest.raises(Validacion):
            pagar(local, pedido_id, [efectivo(1000)] * 3)

    def test_no_se_paga_mas_que_el_saldo(self, local, turno_id):
        pedido_id, _ = pedido_con(local, ("pizza", 1))
        pagar(local, pedido_id, [efectivo(5000)])
        with pytest.raises(Validacion) as error:
            pagar(local, pedido_id, [efectivo(3001)])
        assert error.value.codigo == "MONTO_EXCEDE_SALDO"

    def test_division_por_items_valida_monto_y_unidades(self, local, turno_id):
        pedido_id, (item,) = pedido_con(local, ("bebida", 3))
        with pytest.raises(Validacion) as error:
            pagar(local, pedido_id, [efectivo(1)], tipo_division="items",
                  items_cobrados=[{"item_id": item, "cantidad": 2}])
        assert error.value.codigo == "MONTO_NO_CORRESPONDE"
        pagar(local, pedido_id, [efectivo(3000)], tipo_division="items", items_cobrados=[{"item_id": item, "cantidad": 2}])
        assert local.pedido(L, pedido_id).item(item).cobrado == 2
        # D23: repetido en la lista suma 2 unidades y solo queda 1
        with pytest.raises(Validacion) as error:
            pagar(local, pedido_id, [efectivo(1500)], tipo_division="items",
                  items_cobrados=[{"item_id": item, "cantidad": 1}, {"item_id": item, "cantidad": 1}])
        assert error.value.codigo == "ITEM_SIN_UNIDADES"


class TestFinalizar:
    def test_boleta_cierra_libera_la_mesa_y_deja_el_documento_pendiente(self, local, dynamo, turno_id):
        pedido_id, _ = pedido_con(local, ("pizza", 1))
        with pytest.raises(Validacion) as error:
            ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id, "tipo_documento": "boleta"})
        assert error.value.codigo == "SALDO_PENDIENTE"
        pagar(local, pedido_id, [efectivo(8000, propina=800)])
        r = ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id, "tipo_documento": "boleta"})
        assert r.cuerpo["documento"] == {"tipo": "boleta", "estado": "pendiente"}
        mesa = local.mesa_estado(L, "m1")
        assert (mesa.estado, mesa.pedido_id, mesa.garzon_id) == ("libre", None, None)
        dte = local.obtener("operacion", claves.turno(L, turno_id), claves.sk_dte(pedido_id))
        assert (dte["estado"], dte["total"], dte["GSI1PK"]) == ("pendiente", 8000, claves.VIGILAR_DTE)
        eventos = local.consultar("operacion", claves.eventos(L))
        venta = next(e for e in eventos if e["tipo"] == "venta.cerrada")
        assert venta["datos"]["fecha_operativa"] == local.turno(L, turno_id).fecha_operativa
        assert venta["datos"]["pagos"] == [{"metodo": "efectivo", "monto": 8000, "propina": 800}]

    def test_factura_exige_receptor_valido(self, local, turno_id):
        pedido_id, _ = pedido_con(local, ("pizza", 1))
        pagar(local, pedido_id, [efectivo(8000)])
        with pytest.raises(Validacion) as error:
            ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id, "tipo_documento": "factura",
                                                    "receptor": {"rut": "123", "razon_social": "ACME"}})
        assert error.value.codigo == "RUT_INVALIDO"
        r = ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id, "tipo_documento": "factura",
                                                    "receptor": {"rut": "76.123.456-k", "razon_social": "ACME SpA"}})
        assert r.cuerpo["pedido"]["documento"]["receptor"] == {"rut": "76123456-K", "razon_social": "ACME SpA"}

    def test_finalizar_exige_turno_abierto(self, local):
        pedido_id = ejecutar(local, P.ABRIR, ctx(), {"mesa_id": "m2"}).cuerpo["pedido_id"]
        with pytest.raises(Conflicto) as error:
            ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id})
        assert error.value.codigo == "TURNO_NO_ABIERTO"

    def test_M14_mesa_sin_consumo_se_cierra_sin_documento(self, local, dynamo, turno_id):
        pedido_id = ejecutar(local, P.ABRIR, ctx(), {"mesa_id": "m2"}).cuerpo["pedido_id"]
        r = ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id})
        assert r.cuerpo["documento"] is None
        assert local.mesa_estado(L, "m2").estado == "libre"
        assert contar(dynamo, "operacion", claves.turno(L, turno_id), "DTE#") == 0

    def test_finalizar_dos_veces_es_idempotente_por_estado(self, local, dynamo, turno_id):
        pedido_id, _ = pedido_con(local, ("bebida", 1))
        pagar(local, pedido_id, [efectivo(1500)])
        ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id, "tipo_documento": "boleta"})
        r = ejecutar(local, C.FINALIZAR, cajero(), {"pedido_id": pedido_id, "tipo_documento": "boleta"})
        assert r.cuerpo["pedido"]["estado"] == "cerrado"
        assert contar(dynamo, "operacion", claves.turno(L, turno_id), "DTE#") == 1


class TestTurnoYArqueo:
    def vender(self, local, monto_efectivo=30_000, propina=3000):
        pedido_id, _ = pedido_con(local, ("pizza", 5), ("bebida", 2))  # 43.000
        pagar(local, pedido_id, [efectivo(monto_efectivo, propina=propina),
                                 {"metodo": "credito", "monto": 43_000 - monto_efectivo, "codigo_autorizacion_pos": "Z"}])

    def test_un_solo_turno_abierto(self, local, turno_id):
        with pytest.raises(Conflicto) as error:
            ejecutar(local, C.ABRIR_TURNO, cajero(), {})
        assert error.value.codigo == "TURNO_YA_ABIERTO"

    def test_arqueo_ciego_con_recuento_sobre_el_umbral(self, local, turno_id):
        self.vender(local)  # esperado = 50.000 + 33.000 = 83.000 ; umbral = max(1660, 5000) = 5000
        r = ejecutar(local, C.CONTEO, cajero(), {"turno_id": turno_id, "monto": 83_000 - 5_001})
        assert (r.cuerpo["requiere_segundo_conteo"], r.cuerpo["conteo_completado"]) == (True, False)
        assert "efectivo_esperado" not in r.cuerpo and "resultado" not in r.cuerpo["turno"]
        with pytest.raises(Conflicto) as error:
            ejecutar(local, C.CERRAR_TURNO, cajero(), {"turno_id": turno_id})
        assert error.value.codigo == "FALTA_SEGUNDO_CONTEO"
        r = ejecutar(local, C.CONTEO, cajero(), {"turno_id": turno_id, "monto": 80_000})
        assert r.cuerpo["conteo_completado"] is True
        ejecutar(local, C.CONCILIACION, cajero(), {"turno_id": turno_id, "total_debito_pos": 0,
                                                    "total_credito_pos": 13_000})
        cierre = ejecutar(local, C.CERRAR_TURNO, cajero(), {"turno_id": turno_id}).cuerpo
        assert (cierre["efectivo_esperado"], cierre["conteo_definitivo"], cierre["diferencia_efectivo"]) == \
               (83_000, 80_000, -3_000)
        assert (cierre["total_efectivo_mise"], cierre["total_credito_mise"]) == (33_000, 13_000)
        assert local.turno_abierto(L) is None

    def test_dentro_del_umbral_no_pide_recuento(self, local, turno_id):
        self.vender(local)
        r = ejecutar(local, C.CONTEO, cajero(), {"turno_id": turno_id, "monto": 83_000 + 5_000})
        assert r.cuerpo["conteo_completado"] is True

    def test_un_pago_entre_conteo_y_cierre_se_refleja_en_el_esperado(self, local, turno_id):
        ejecutar(local, C.CONTEO, cajero(), {"turno_id": turno_id, "monto": 50_000})
        self.vender(local, monto_efectivo=10_000, propina=0)
        ejecutar(local, C.CONCILIACION, cajero(), {"turno_id": turno_id, "total_debito_pos": 0, "total_credito_pos": 0})
        cierre = ejecutar(local, C.CERRAR_TURNO, cajero(), {"turno_id": turno_id}).cuerpo
        assert cierre["efectivo_esperado"] == 60_000

    def test_turno_cerrado_no_recibe_pagos(self, local, turno_id):
        ejecutar(local, C.CONTEO, cajero(), {"turno_id": turno_id, "monto": 50_000})
        ejecutar(local, C.CONCILIACION, cajero(), {"turno_id": turno_id, "total_debito_pos": 0, "total_credito_pos": 0})
        ejecutar(local, C.CERRAR_TURNO, cajero(), {"turno_id": turno_id})
        pedido_id, _ = pedido_con(local, ("bebida", 1))
        with pytest.raises(Conflicto):
            pagar(local, pedido_id, [efectivo(1500)])


class TestRetiros:
    def retiro(self, local, codigo, autorizador="admin1", **extra):
        return ejecutar(local, C.RETIRO, cajero(**extra), {"monto": 4000, "motivo": "hielo",
                                                           "autorizador_id": autorizador, "codigo": codigo})

    def test_retiro_autorizado_resta_del_esperado_y_audita(self, local, dynamo, turno_id):
        r = self.retiro(local, CODIGO_ADMIN)
        assert (r.http, r.cuerpo["autorizado_por"]) == (201, "admin1")
        assert local.turno(L, turno_id).efectivo_esperado == 46_000
        tipos = [e["tipo"] for e in local.consultar("operacion", claves.eventos(L))]
        assert "autorizacion.concedida" in tipos

    def test_D12_codigo_invalido_es_403_y_no_cierra_sesion(self, local, turno_id):
        with pytest.raises(Prohibido) as error:
            self.retiro(local, "0000")
        assert error.value.http == 403 and error.value.codigo == "CODIGO_AUTORIZACION_INVALIDO"
        assert error.value.detalle["intentos_restantes"] == 4

    def test_un_cajero_no_puede_autorizar(self, local, turno_id):
        with pytest.raises(Prohibido) as error:
            self.retiro(local, CODIGO_ADMIN, autorizador="cajero1")
        assert error.value.codigo == "AUTORIZADOR_INVALIDO"

    def test_bloqueo_tras_cinco_intentos_aun_con_el_codigo_correcto(self, local, turno_id):
        for _ in range(autorizacion.MAX_INTENTOS):
            with pytest.raises(Prohibido):
                self.retiro(local, "0000")
        with pytest.raises(Prohibido) as error:
            self.retiro(local, CODIGO_ADMIN)
        assert error.value.codigo == "AUTORIZACION_BLOQUEADA"
        # El bloqueo es por autorizador: otro admin sí puede autorizar.
        assert self.retiro(local, CODIGO_ADMIN, autorizador="dueno1").http == 201

    def test_reintentar_el_mismo_comando_fallido_no_suma_otro_intento(self, local, turno_id):
        contexto = cajero()
        cuerpo = {"monto": 4000, "motivo": "hielo", "autorizador_id": "admin1", "codigo": "0000"}
        with pytest.raises(Prohibido) as error:
            ejecutar(local, C.RETIRO, contexto, cuerpo)
        for _ in range(2):
            # La repetición devuelve la respuesta guardada (M9), no vuelve a evaluar el código.
            repetida = ejecutar(local, C.RETIRO, contexto, cuerpo)
            assert (repetida.http, repetida.cuerpo, repetida.repetida) == (403, error.value.cuerpo(), True)
        assert local.bloqueo(L, "admin1").intentos == 1
