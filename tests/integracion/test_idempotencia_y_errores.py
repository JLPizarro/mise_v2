"""Idempotencia por X-Command-Id, concurrencia optimista y clasificación de errores de DynamoDB."""

from decimal import Decimal

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from pos_dominio import claves
from pos_dominio.cambios import Crear
from pos_dominio.ejecutor import ejecutar
from pos_dominio.errores import (
    ComandoDuplicado, Conflicto, ErrorDeCodigo, ErrorInfraestructura, Reintentar, Validacion,
)
from pos_dominio.infra.dynamodb import AlmacenDynamo, _clasificar_cancelacion, a_item, desde_item
from pos_dominio.operaciones import caja as C
from pos_dominio.operaciones import pedidos as P

from integracion.semilla import L, contar, ctx, sembrar


@pytest.fixture
def local(dynamo, almacen):
    sembrar(dynamo)
    return almacen


class TestIdempotencia:
    def test_el_mismo_command_id_escribe_una_sola_vez(self, local, dynamo):
        pedido_id = ejecutar(local, P.ABRIR, ctx(), {"mesa_id": "m1"}).cuerpo["pedido_id"]
        contexto = ctx()
        cuerpo = {"pedido_id": pedido_id, "producto_id": "pizza"}
        primera = ejecutar(local, P.AGREGAR_ITEM, contexto, cuerpo)
        segunda = ejecutar(local, P.AGREGAR_ITEM, contexto, cuerpo)
        assert (segunda.http, segunda.cuerpo, segunda.repetida) == (primera.http, primera.cuerpo, True)
        assert contar(dynamo, "operacion", claves.pedido(L, pedido_id), "ITEM#") == 1
        assert local.pedido(L, pedido_id).total == 8000
        assert sum(1 for e in local.consultar("operacion", claves.eventos(L)) if e["tipo"] == "item.agregado") == 1

    def test_reutilizar_el_id_con_otro_cuerpo_es_422(self, local):
        pedido_id = ejecutar(local, P.ABRIR, ctx(), {"mesa_id": "m1"}).cuerpo["pedido_id"]
        contexto = ctx()
        ejecutar(local, P.AGREGAR_ITEM, contexto, {"pedido_id": pedido_id, "producto_id": "pizza"})
        with pytest.raises(Validacion) as error:
            ejecutar(local, P.AGREGAR_ITEM, contexto, {"pedido_id": pedido_id, "producto_id": "bebida"})
        assert error.value.codigo == "COMANDO_REUTILIZADO"

    def test_command_id_debe_ser_ulid(self, local):
        with pytest.raises(Validacion) as error:
            ejecutar(local, P.ABRIR, ctx(command_id="no-es-ulid"), {"mesa_id": "m1"})
        assert error.value.codigo == "COMMAND_ID_INVALIDO"

    def test_duplicado_detectado_dentro_de_la_transaccion(self, local):
        # Dos peticiones simultáneas con el mismo ID pasan la lectura previa; la condición del CMD
        # (primer ítem de la transacción) detiene a la segunda.
        contexto = ctx()
        argumentos = dict(http=201, respuesta={}, estado_cmd="aplicado", eventos=[])
        local.aplicar(contexto, "prueba", "h", cambios=[], **argumentos)
        with pytest.raises(ComandoDuplicado):
            local.aplicar(contexto, "prueba", "h", cambios=[], **argumentos)


class _Interferencia(AlmacenDynamo):
    """Ejecuta otra operación justo antes de la primera escritura, para forzar una carrera."""

    def __init__(self, base: AlmacenDynamo, accion):
        super().__init__(base.cliente, dormir=lambda _: None)
        self._accion = accion

    def aplicar(self, *args, **kwargs):
        if self._accion:
            accion, self._accion = self._accion, None
            accion()
        return super().aplicar(*args, **kwargs)


class TestConcurrencia:
    def test_version_cambiada_se_relee_y_se_aplica(self, local):
        pedido_id = ejecutar(local, P.ABRIR, ctx(), {"mesa_id": "m1"}).cuerpo["pedido_id"]
        otro = lambda: ejecutar(local, P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, "producto_id": "bebida"})  # noqa: E731
        ejecutar(_Interferencia(local, otro), P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, "producto_id": "pizza"})
        pedido = local.pedido(L, pedido_id)
        assert (pedido.total, pedido.n_items, len(pedido.items)) == (9500, 2, 2)

    def test_D6_dos_cobros_simultaneos_no_superan_el_total(self, local):
        ejecutar(local, C.ABRIR_TURNO, ctx("cajero1", "cajero"), {})
        pedido_id = ejecutar(local, P.ABRIR, ctx(), {"mesa_id": "m1"}).cuerpo["pedido_id"]
        ejecutar(local, P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, "producto_id": "pizza"})
        pago = {"pedido_id": pedido_id, "medios": [{"metodo": "transferencia", "monto": 8000}]}
        otra_caja = lambda: ejecutar(local, C.REGISTRAR_PAGO, ctx("cajero1", "cajero"), pago)  # noqa: E731
        with pytest.raises(Validacion) as error:
            ejecutar(_Interferencia(local, otra_caja), C.REGISTRAR_PAGO, ctx("admin1", "admin"), pago)
        assert error.value.codigo == "MONTO_EXCEDE_SALDO"
        assert local.pedido(L, pedido_id).pagado == 8000

    def test_D5_dos_garzones_abren_la_misma_mesa_y_queda_un_pedido(self, local):
        otro = {}
        primero = lambda: otro.setdefault("r", ejecutar(local, P.ABRIR, ctx("garzon2"), {"mesa_id": "m1"}))  # noqa: E731
        segundo = ejecutar(_Interferencia(local, primero), P.ABRIR, ctx("garzon1"), {"mesa_id": "m1"})
        assert segundo.cuerpo["pedido_id"] == otro["r"].cuerpo["pedido_id"]
        assert local.mesa_estado(L, "m1").garzon_id == "garzon2"


class _ClienteQueFalla:
    def __init__(self, error):
        self.error = error
        self.llamadas = 0

    def transact_write_items(self, **_):
        self.llamadas += 1
        raise self.error


def _cancelada(*motivos):
    return ClientError({"Error": {"Code": "TransactionCanceledException", "Message": "x"},
                        "CancellationReasons": [{"Code": m} for m in motivos]}, "TransactWriteItems")


class TestClasificacionDeErrores:
    def aplicar(self, error):
        cliente = _ClienteQueFalla(error)
        almacen = AlmacenDynamo(cliente, dormir=lambda _: None)
        cambio = Crear(tabla="operacion", pk="P", sk="S", atributos={})
        try:
            almacen.aplicar(ctx(), "prueba", "h", http=200, respuesta={}, estado_cmd="aplicado", cambios=[cambio],
                            eventos=[])
        finally:
            self.llamadas = cliente.llamadas

    @pytest.mark.parametrize("codigo", ["ProvisionedThroughputExceededException", "ThrottlingException",
                                        "InternalServerError", "RequestLimitExceeded", "AccessDeniedException"])
    def test_errores_de_aws_son_infraestructura(self, codigo):
        with pytest.raises(ErrorInfraestructura):
            self.aplicar(ClientError({"Error": {"Code": codigo, "Message": "x"}}, "TransactWriteItems"))

    def test_tiempo_agotado_es_infraestructura(self):
        with pytest.raises(ErrorInfraestructura):
            self.aplicar(ReadTimeoutError(endpoint_url="https://dynamodb"))

    def test_validation_exception_es_defecto_de_codigo(self):
        with pytest.raises(ErrorDeCodigo):
            self.aplicar(ClientError({"Error": {"Code": "ValidationException", "Message": "x"}}, "TransactWriteItems"))

    @pytest.mark.parametrize("motivo", ["ThrottlingError", "ProvisionedThroughputExceeded", "InternalServerError"])
    def test_cancelacion_por_limitacion_es_infraestructura(self, motivo):
        with pytest.raises(ErrorInfraestructura):
            self.aplicar(_cancelada("None", motivo))

    def test_conflicto_de_transaccion_se_reintenta_y_luego_es_infraestructura(self):
        with pytest.raises(ErrorInfraestructura):
            self.aplicar(_cancelada("None", "TransactionConflict"))
        assert self.llamadas == 3

    def test_condicion_de_negocio(self):
        error_negocio = Conflicto("x", codigo="TURNO_YA_ABIERTO")
        cambio = Crear(tabla="operacion", pk="P", sk="S", atributos={}, al_fallar=error_negocio)
        assert _clasificar_cancelacion(["None", "ConditionalCheckFailed"], ["cmd", cambio]) is error_negocio

    def test_condicion_de_version_pide_releer(self):
        cambio = Crear(tabla="operacion", pk="P", sk="S", atributos={}, reintentar=True)
        assert isinstance(_clasificar_cancelacion(["None", "ConditionalCheckFailed"], ["cmd", cambio]), Reintentar)

    def test_condicion_del_cmd_es_duplicado(self):
        assert isinstance(_clasificar_cancelacion(["ConditionalCheckFailed", "None"], ["cmd", None]), ComandoDuplicado)

    def test_mas_de_100_items_se_detecta_antes_de_enviar(self, almacen):
        cambios = [Crear(tabla="operacion", pk=f"P{i}", sk="S", atributos={}) for i in range(100)]
        with pytest.raises(ErrorDeCodigo):
            almacen.aplicar(ctx(), "prueba", "h", http=200, respuesta={}, estado_cmd="aplicado", cambios=cambios,
                            eventos=[])


class TestSerializacion:
    def test_float_se_rechaza_antes_de_llegar_a_dynamodb(self):
        with pytest.raises(ErrorDeCodigo, match="detalle.monto"):
            a_item({"detalle": {"monto": 1.5}})

    def test_decimal_se_convierte_a_int(self):
        datos = desde_item({"total": {"N": "11000"}, "lista": {"L": [{"N": "1"}, {"M": {"x": {"N": "2"}}}]}})
        assert datos == {"total": 11000, "lista": [1, {"x": 2}]}
        assert type(datos["total"]) is int

    def test_respuesta_guardada_no_contiene_decimal(self, local):
        contexto = ctx()
        ejecutar(local, P.ABRIR, contexto, {"mesa_id": "m1"})
        cmd = local.leer_comando(L, contexto.command_id)
        assert isinstance(cmd["respuesta"], str) and type(cmd["http_status"]) is int
        assert not isinstance(cmd["http_status"], Decimal)
