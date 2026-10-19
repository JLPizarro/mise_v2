"""Caracterización de pagos, arqueo ciego y retiros en el POS local (copia congelada en legado/)."""

import pytest

from app.application.use_cases.caja_use_cases import (
    AbrirTurnoUseCase,
    CerrarTurnoUseCase,
    RegistrarConciliacionTerminalUseCase,
    RegistrarConteoEfectivoUseCase,
    RegistrarRetiroUseCase,
    calcular_umbral_diferencia,
)
from app.application.use_cases.pagos_use_cases import RegistrarPagoUseCase
from app.domain.entities import ItemCobrado
from app.domain.exceptions import NotFoundError, UnauthorizedError, ValidationError

from caracterizacion.dobles import (
    ConfiguracionEnMemoria,
    MesasEnMemoria,
    PagosEnMemoria,
    PedidosEnMemoria,
    ProductosEnMemoria,
    RetirosEnMemoria,
    TurnosEnMemoria,
    UsuariosEnMemoria,
)


@pytest.fixture
def pos():
    class Pos:
        pass

    p = Pos()
    p.mesas = MesasEnMemoria()
    p.mesas.agregar("m1")
    p.productos = ProductosEnMemoria()
    p.productos.agregar("pizza", 8000)
    p.productos.agregar("bebida", 1500)
    p.pedidos = PedidosEnMemoria(p.productos)
    p.pagos = PagosEnMemoria()
    p.turnos = TurnosEnMemoria()
    p.retiros = RetirosEnMemoria()
    p.config = ConfiguracionEnMemoria()
    p.usuarios = UsuariosEnMemoria()
    return p


def pedido_con(pos, *lineas):
    pedido = pos.pedidos.create("m1", "g1")
    items = [pos.pedidos.add_item(pedido.pedido_id, prod, None, cant, None,
                                  pos.productos.productos[prod].precio) for prod, cant in lineas]
    return pedido.pedido_id, items


def pagar(pos, pedido_id, monto, metodo="efectivo", propina=0, codigo=None, division="completa",
          items=None, turno_id="t1"):
    return RegistrarPagoUseCase(pos.pagos, pos.pedidos).execute(
        "m1", metodo, monto, propina, pedido_id, turno_id, codigo, None, None, None, None, division, None,
        items)


class TestValidacionesDePago:
    @pytest.mark.parametrize("metodo", ["cheque", "", "EFECTIVO"])
    def test_metodo_invalido(self, pos, metodo):
        pedido_id, _ = pedido_con(pos, ("pizza", 1))
        with pytest.raises(ValidationError, match="metodo de pago inválido"):
            pagar(pos, pedido_id, 1000, metodo=metodo)

    @pytest.mark.parametrize("monto", [0, -5])
    def test_monto_positivo(self, pos, monto):
        pedido_id, _ = pedido_con(pos, ("pizza", 1))
        with pytest.raises(ValidationError, match="monto debe ser mayor a 0"):
            pagar(pos, pedido_id, monto)

    @pytest.mark.parametrize("metodo", ["debito", "credito"])
    def test_tarjeta_exige_codigo(self, pos, metodo):
        pedido_id, _ = pedido_con(pos, ("pizza", 1))
        with pytest.raises(ValidationError, match="codigo_autorizacion_pos"):
            pagar(pos, pedido_id, 1000, metodo=metodo)

    def test_transferencia_no_exige_codigo(self, pos):
        pedido_id, _ = pedido_con(pos, ("pizza", 1))
        assert pagar(pos, pedido_id, 8000, metodo="transferencia").monto == 8000

    def test_division_invalida(self, pos):
        pedido_id, _ = pedido_con(pos, ("pizza", 1))
        with pytest.raises(ValidationError, match="tipo_division inválido"):
            pagar(pos, pedido_id, 1000, division="mitad")

    def test_pedido_inexistente(self, pos):
        with pytest.raises(NotFoundError):
            pagar(pos, "no_existe", 1000)

    def test_monto_mayor_al_saldo(self, pos):
        pedido_id, _ = pedido_con(pos, ("pizza", 1))
        with pytest.raises(ValidationError, match="excede el saldo pendiente"):
            pagar(pos, pedido_id, 8001)

    def test_D7_sin_pedido_no_se_valida_saldo(self, pos):
        assert pagar(pos, None, 999_999).monto == 999_999


class TestPagosMixtosYDivision:
    def test_pagos_mixtos_suman_hasta_el_total_y_la_propina_no_consume_saldo(self, pos):
        pedido_id, _ = pedido_con(pos, ("pizza", 1), ("bebida", 2))  # total 11000
        pagar(pos, pedido_id, 6000, metodo="debito", codigo="A1")
        pagar(pos, pedido_id, 5000, metodo="efectivo", propina=1100)
        with pytest.raises(ValidationError, match="excede el saldo pendiente"):
            pagar(pos, pedido_id, 1)

    def test_por_items_no_permite_cobrar_mas_unidades_de_las_que_quedan(self, pos):
        pedido_id, items = pedido_con(pos, ("bebida", 3))
        pagar(pos, pedido_id, 3000, division="items", items=[ItemCobrado(items[0].item_id, 2)])
        # Queda 1 unidad y $1.500 de saldo: el saldo se valida antes que las unidades.
        with pytest.raises(ValidationError, match="excede lo disponible"):
            pagar(pos, pedido_id, 1500, division="items", items=[ItemCobrado(items[0].item_id, 2)])

    def test_por_items_rechaza_items_ajenos(self, pos):
        pedido_id, _ = pedido_con(pos, ("bebida", 1))
        with pytest.raises(ValidationError, match="no pertenece a este pedido"):
            pagar(pos, pedido_id, 1500, division="items", items=[ItemCobrado("ajeno", 1)])

    def test_por_items_no_valida_que_el_monto_corresponda_a_los_items(self, pos):
        pedido_id, items = pedido_con(pos, ("pizza", 1))
        pago = pagar(pos, pedido_id, 1, division="items", items=[ItemCobrado(items[0].item_id, 1)])
        assert pago.monto == 1

    def test_por_items_un_mismo_item_repetido_en_la_lista_se_valida_por_separado(self, pos):
        pedido_id, items = pedido_con(pos, ("bebida", 3))
        repetido = [ItemCobrado(items[0].item_id, 2), ItemCobrado(items[0].item_id, 2)]
        assert pagar(pos, pedido_id, 4500, division="items", items=repetido).items_cobrados == repetido

    def test_unidades_cobradas_cuentan_de_cualquier_division(self, pos):
        # El backend suma items_cobrados de todos los pagos previos, sin mirar tipo_division.
        pedido_id, items = pedido_con(pos, ("bebida", 2))
        pagar(pos, pedido_id, 1500, division="monto_libre", items=[ItemCobrado(items[0].item_id, 2)])
        with pytest.raises(ValidationError, match="excede lo disponible"):
            pagar(pos, pedido_id, 1500, division="items", items=[ItemCobrado(items[0].item_id, 1)])


class TestUmbral:
    @pytest.mark.parametrize("esperado,pct,minimo,umbral", [
        (100_000, 2.0, 5000, 5000),
        (1_000_000, 2.0, 5000, 20000),
        (250_000, 2.0, 5000, 5000),
        (250_025, 2.0, 0, 5000),     # 5000,5 -> round() de Python redondea al par: 5000
        (250_075, 2.0, 0, 5002),     # 5001,5 -> 5002
        (0, 2.0, 5000, 5000),
    ])
    def test_umbral_mayor_entre_porcentaje_y_minimo_con_redondeo_al_par(self, esperado, pct, minimo, umbral):
        assert calcular_umbral_diferencia(esperado, pct, minimo) == umbral


class TestArqueoCiego:
    def preparar(self, pos, apertura=50_000):
        turno = AbrirTurnoUseCase(pos.turnos).execute("cajero", apertura)
        pedido_id, _ = pedido_con(pos, ("pizza", 10))  # 80.000
        pagar(pos, pedido_id, 30_000, metodo="efectivo", propina=3000, turno_id=turno.turno_id)
        pagar(pos, pedido_id, 20_000, metodo="debito", propina=2000, codigo="X", turno_id=turno.turno_id)
        pagar(pos, pedido_id, 10_000, metodo="credito", codigo="Y", turno_id=turno.turno_id)
        pagar(pos, pedido_id, 5_000, metodo="transferencia", turno_id=turno.turno_id)
        pos.retiros.create(turno.turno_id, "cajero", "admin", 4_000, "hielo")
        # esperado = 50.000 + (30.000 + 3.000) - 4.000 = 79.000 ; umbral = max(1580, 5000) = 5000
        return turno.turno_id

    def conteo(self, pos, turno_id, monto):
        return RegistrarConteoEfectivoUseCase(pos.turnos, pos.pagos, pos.retiros, pos.config).execute(
            turno_id, monto)

    def test_apertura_negativa(self, pos):
        with pytest.raises(ValidationError):
            AbrirTurnoUseCase(pos.turnos).execute("cajero", -1)

    def test_un_solo_turno_abierto(self, pos):
        AbrirTurnoUseCase(pos.turnos).execute("cajero", 0)
        with pytest.raises(ValidationError, match="Ya hay un turno de caja abierto"):
            AbrirTurnoUseCase(pos.turnos).execute("cajero", 0)

    def test_diferencia_igual_al_umbral_no_pide_recuento(self, pos):
        turno_id = self.preparar(pos)
        r = self.conteo(pos, turno_id, 79_000 + 5_000)
        assert (r.requiere_segundo_conteo, r.conteo_completado) == (False, True)

    def test_diferencia_sobre_el_umbral_pide_recuento(self, pos):
        turno_id = self.preparar(pos)
        r = self.conteo(pos, turno_id, 79_000 - 5_001)
        assert (r.requiere_segundo_conteo, r.conteo_completado) == (True, False)
        assert r.turno.requiere_segundo_conteo is True

    def test_el_recuento_se_acepta_aunque_siga_fuera_y_es_definitivo(self, pos):
        turno_id = self.preparar(pos)
        self.conteo(pos, turno_id, 60_000)
        r = self.conteo(pos, turno_id, 61_000)
        assert (r.requiere_segundo_conteo, r.conteo_completado) == (False, True)
        RegistrarConciliacionTerminalUseCase(pos.turnos).execute(turno_id, 22_000, 10_000, 0)
        cierre = CerrarTurnoUseCase(pos.turnos, pos.pagos, pos.retiros).execute(turno_id, "cajero")
        assert cierre.conteo_definitivo == 61_000
        assert cierre.diferencia_efectivo == 61_000 - 79_000

    def test_no_se_repite_el_primer_conteo(self, pos):
        turno_id = self.preparar(pos)
        self.conteo(pos, turno_id, 79_000)
        with pytest.raises(ValidationError, match="primer conteo ya fue registrado"):
            self.conteo(pos, turno_id, 79_000)

    def test_conteo_negativo(self, pos):
        turno_id = self.preparar(pos)
        with pytest.raises(ValidationError):
            self.conteo(pos, turno_id, -1)

    def test_cierre_exige_pasos_en_orden(self, pos):
        turno_id = self.preparar(pos)
        cerrar = CerrarTurnoUseCase(pos.turnos, pos.pagos, pos.retiros)
        with pytest.raises(ValidationError, match="Falta registrar el conteo de efectivo"):
            cerrar.execute(turno_id, "cajero")
        self.conteo(pos, turno_id, 70_000)
        with pytest.raises(ValidationError, match="Falta registrar el segundo conteo"):
            cerrar.execute(turno_id, "cajero")
        self.conteo(pos, turno_id, 79_000)
        with pytest.raises(ValidationError, match="Falta registrar la conciliación"):
            cerrar.execute(turno_id, "cajero")

    def test_resultado_del_cierre_incluye_propinas_por_medio(self, pos):
        turno_id = self.preparar(pos)
        self.conteo(pos, turno_id, 79_000)
        RegistrarConciliacionTerminalUseCase(pos.turnos).execute(turno_id, 22_000, 10_000, 0)
        r = CerrarTurnoUseCase(pos.turnos, pos.pagos, pos.retiros).execute(turno_id, "cajero")
        assert (r.efectivo_esperado, r.conteo_definitivo, r.diferencia_efectivo) == (79_000, 79_000, 0)
        assert (r.total_efectivo_mise, r.total_debito_mise, r.total_credito_mise) == (33_000, 22_000, 10_000)
        assert r.turno.estado == "cerrado"

    def test_la_conciliacion_se_puede_sobrescribir(self, pos):
        turno_id = self.preparar(pos)
        RegistrarConciliacionTerminalUseCase(pos.turnos).execute(turno_id, 1, 1, 1)
        t = RegistrarConciliacionTerminalUseCase(pos.turnos).execute(turno_id, 2, 2, 2)
        assert t.total_debito_pos == 2


class TestRetiros:
    def preparar(self, pos):
        pos.usuarios.agregar("admin1", "admin", pin="1234")
        pos.usuarios.agregar("admin2", "admin", pin="1234")
        pos.usuarios.agregar("cajero1", "cajero", pin="9999")
        return AbrirTurnoUseCase(pos.turnos).execute("cajero1", 0).turno_id

    def retiro(self, pos, turno_id, monto=1000, motivo="hielo", codigo="1234"):
        return RegistrarRetiroUseCase(pos.retiros, pos.turnos, pos.usuarios).execute(
            turno_id, "cajero1", monto, motivo, codigo)

    def test_D13_con_codigos_repetidos_autoriza_el_primero_que_calza(self, pos):
        assert self.retiro(pos, self.preparar(pos)).autorizado_por == "admin1"

    def test_codigo_de_cajero_no_autoriza(self, pos):
        with pytest.raises(UnauthorizedError):
            self.retiro(pos, self.preparar(pos), codigo="9999")

    def test_D12_codigo_invalido_es_no_autenticado(self, pos):
        # En HTTP se traduce a 401, y el frontend cierra la sesión del cajero al recibirlo.
        with pytest.raises(UnauthorizedError):
            self.retiro(pos, self.preparar(pos), codigo="0000")

    def test_validaciones(self, pos):
        turno_id = self.preparar(pos)
        with pytest.raises(ValidationError):
            self.retiro(pos, turno_id, monto=0)
        with pytest.raises(ValidationError, match="motivo"):
            self.retiro(pos, turno_id, motivo="  ")

    def test_motivo_se_guarda_sin_espacios(self, pos):
        assert self.retiro(pos, self.preparar(pos), motivo="  hielo  ").motivo == "hielo"
