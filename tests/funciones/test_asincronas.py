"""Funciones asíncronas: procesador-eventos, emision-dte, drenador-contingencia y tareas-programadas."""

import gzip
import json
from datetime import timedelta

import pytest

from pos_dominio import claves, ids, tiempo
from pos_dominio.ejecutor import ejecutar
from pos_dominio.infra import aws
from pos_dominio.operaciones import caja as C
from pos_dominio.operaciones import pedidos as P

from funciones.utiles import cargar
from integracion.semilla import L, LOCAL, TENANT, ctx


def _cajero():
    return ctx("cajero1", "cajero")


def vender(total_items=(("pizza", 1),), tipo="boleta", conteo=None, cerrar=False):
    """Venta completa con el dominio; devuelve (pedido_id, turno_id)."""
    almacen = aws.almacen()
    turno = almacen.turno_abierto(L)
    turno_id = turno.turno_id if turno else ejecutar(almacen, C.ABRIR_TURNO, _cajero(), {"monto_apertura": 0}).cuerpo["turno_id"]
    mesa = "m1" if almacen.mesa_estado(L, "m1") is None or almacen.mesa_estado(L, "m1").estado == "libre" else "m2"
    pedido_id = ejecutar(almacen, P.ABRIR, ctx(), {"mesa_id": mesa}).cuerpo["pedido_id"]
    for producto, cantidad in total_items:
        ejecutar(almacen, P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, "producto_id": producto, "cantidad": cantidad})
    total = almacen.pedido(L, pedido_id).total
    ejecutar(almacen, C.REGISTRAR_PAGO, _cajero(), {"pedido_id": pedido_id, "medios": [
        {"metodo": "efectivo", "monto": total, "propina": 500, "efectivo_recibido": total + 500}]})
    ejecutar(almacen, C.FINALIZAR, _cajero(), {"pedido_id": pedido_id, "tipo_documento": tipo})
    if cerrar:
        r = ejecutar(almacen, C.CONTEO, _cajero(), {"turno_id": turno_id, "monto": conteo})
        if r.cuerpo["requiere_segundo_conteo"]:
            ejecutar(almacen, C.CONTEO, _cajero(), {"turno_id": turno_id, "monto": conteo})
        ejecutar(almacen, C.CONCILIACION, _cajero(), {"turno_id": turno_id, "total_debito_pos": 0, "total_credito_pos": 0})
        ejecutar(almacen, C.CERRAR_TURNO, _cajero(), {"turno_id": turno_id})
    return pedido_id, turno_id


def registros_stream(nube, desde: int = 0) -> list[dict]:
    """Los EVT# de la tabla como los entregaría DynamoDB Streams (NEW_IMAGE)."""
    items = nube.dynamo.query(TableName="operacion", KeyConditionExpression="PK = :pk",
                              ExpressionAttributeValues={":pk": {"S": claves.eventos(L)}})["Items"]
    return [{"eventID": str(i), "eventName": "INSERT",
             "dynamodb": {"Keys": {"PK": item["PK"], "SK": item["SK"]}, "NewImage": item, "SequenceNumber": str(1000 + i)}}
            for i, item in enumerate(items)][desde:]


def mensajes(nube, cola: str) -> list[dict]:
    respuesta = nube.sqs.receive_message(QueueUrl=cola, MaxNumberOfMessages=10, AttributeNames=["All"])
    return respuesta.get("Messages", [])


class TestProcesadorEventos:
    def test_efectos_de_una_venta(self, nube):
        procesador = cargar("procesador-eventos")
        pedido_id, turno_id = vender((("pizza", 2),))
        assert procesador.lambda_handler({"Records": registros_stream(nube)}) == {"batchItemFailures": []}
        almacen = aws.almacen()
        resumen = almacen.obtener("operacion", claves.turno(L, turno_id), "AGG#RESUMEN")
        assert (resumen["n_ventas"], resumen["total_ventas"], resumen["monto_efectivo"], resumen["propina_efectivo"]) == \
               (1, 16000, 16000, 500)
        assert almacen.obtener("operacion", claves.turno(L, turno_id), "AGG#GARZON#garzon1")["total_ventas"] == 16000
        objetos = [o["Key"] for o in nube.s3.list_objects_v2(Bucket=nube.bucket)["Contents"]]
        assert any(k.startswith(f"comprobantes/tenant={TENANT}/local={LOCAL}/") and k.endswith(f"{pedido_id}.html")
                   for k in objetos)
        archivo = next(k for k in objetos if k.startswith("eventos/"))
        fila = json.loads(gzip.decompress(nube.s3.get_object(Bucket=nube.bucket, Key=archivo)["Body"].read()))
        assert fila["tenant_id"] == TENANT and "datos" in fila
        dte = [json.loads(m["Body"]) for m in mensajes(nube, nube.cola_dte)]
        assert dte == [{"tenant_id": TENANT, "local_id": LOCAL, "turno_id": turno_id, "venta_id": pedido_id}]

    def test_reprocesar_el_mismo_lote_no_cuenta_dos_veces(self, nube):
        procesador = cargar("procesador-eventos")
        _, turno_id = vender()
        lote = {"Records": registros_stream(nube)}
        procesador.lambda_handler(lote)
        procesador.lambda_handler(lote)
        assert aws.almacen().obtener("operacion", claves.turno(L, turno_id), "AGG#RESUMEN")["n_ventas"] == 1

    def test_ignora_lo_que_no_es_un_evento(self, nube):
        procesador = cargar("procesador-eventos")
        registro = {"eventName": "INSERT", "dynamodb": {"SequenceNumber": "1", "NewImage": {
            "PK": {"S": "x"}, "SK": {"S": "y"}, "tipo_item": {"S": "PEDIDO"}}}}
        assert procesador.lambda_handler({"Records": [registro]}) == {"batchItemFailures": []}

    def test_falla_reporta_el_registro_para_reintentar_desde_ahi(self, nube, monkeypatch):
        procesador = cargar("procesador-eventos")
        vender()
        registros = registros_stream(nube)
        monkeypatch.setenv("BUCKET_ARCHIVO", "bucket-que-no-existe")
        resultado = procesador.lambda_handler({"Records": registros})
        assert resultado == {"batchItemFailures": [{"itemIdentifier": registros[0]["dynamodb"]["SequenceNumber"]}]}

    def test_cierre_con_diferencia_avisa_al_dueno_una_vez(self, nube, monkeypatch):
        procesador = cargar("procesador-eventos")
        publicados = []
        monkeypatch.setattr(aws, "publicar", lambda tema, asunto, mensaje, **_: publicados.append((tema, asunto)))
        vender(conteo=1_000, cerrar=True)
        lote = {"Records": registros_stream(nube)}
        procesador.lambda_handler(lote)
        procesador.lambda_handler(lote)
        assert [a for _, a in publicados] == ["MISE: cierre de caja con observaciones"]


class TestEmisionDte:
    def mensaje(self, pedido_id, turno_id, recepcion=1):
        return {"Records": [{"messageId": "m1", "receiptHandle": "r1",
                             "attributes": {"ApproximateReceiveCount": str(recepcion)},
                             "body": json.dumps({"tenant_id": TENANT, "local_id": LOCAL, "turno_id": turno_id,
                                                 "venta_id": pedido_id})}]}

    def dte(self, pedido_id, turno_id):
        return aws.almacen().obtener("operacion", claves.turno(L, turno_id), claves.sk_dte(pedido_id))

    def test_emitido_con_folio_e_impresion_en_caja(self, nube, dynamo_impresora_caja):
        funcion = cargar("emision-dte")
        pedido_id, turno_id = vender()
        assert funcion.lambda_handler(self.mensaje(pedido_id, turno_id)) == {"batchItemFailures": []}
        dte = self.dte(pedido_id, turno_id)
        assert (dte["estado"], dte["folio"]) == ("emitido", 1) and dte["timbre"]
        assert "GSI1PK" not in dte
        trabajos = aws.almacen().listar("operacion", claves.impresora(L, "imp_caja"), "PEND#")
        assert [t["trabajo_id"] for t in trabajos] == [f"DTE-{pedido_id}"]
        # Idempotente: el mismo mensaje otra vez no cambia el folio ni imprime de nuevo.
        funcion.lambda_handler(self.mensaje(pedido_id, turno_id))
        assert self.dte(pedido_id, turno_id)["folio"] == 1
        assert len(aws.almacen().listar("operacion", claves.impresora(L, "imp_caja"), "PEND#")) == 1

    def test_folios_correlativos_por_tipo(self, nube):
        funcion = cargar("emision-dte")
        ventas = [vender() for _ in range(2)]
        for pedido_id, turno_id in ventas:
            funcion.lambda_handler(self.mensaje(pedido_id, turno_id))
        assert sorted(self.dte(p, t)["folio"] for p, t in ventas) == [1, 2]

    def test_rechazo_no_se_reintenta(self, nube, monkeypatch):
        monkeypatch.setenv("DTE_MODO", "rechazo")
        funcion = cargar("emision-dte")
        pedido_id, turno_id = vender()
        assert funcion.lambda_handler(self.mensaje(pedido_id, turno_id)) == {"batchItemFailures": []}
        assert self.dte(pedido_id, turno_id)["estado"] == "rechazado"

    @pytest.mark.parametrize("modo", ["error5xx", "limite429", "timeout"])
    def test_falla_transitoria_se_reintenta_y_en_la_ultima_queda_fallido(self, nube, monkeypatch, modo):
        monkeypatch.setenv("DTE_MODO", modo)
        funcion = cargar("emision-dte")
        visibilidades = []
        monkeypatch.setattr(aws, "cambiar_visibilidad", lambda cola, recibo, s: visibilidades.append(s))
        pedido_id, turno_id = vender()
        assert funcion.lambda_handler(self.mensaje(pedido_id, turno_id, 1))["batchItemFailures"] == [{"itemIdentifier": "m1"}]
        assert self.dte(pedido_id, turno_id)["estado"] == "enviando" and visibilidades and visibilidades[0] >= 24
        assert funcion.lambda_handler(self.mensaje(pedido_id, turno_id, 5))["batchItemFailures"] == [{"itemIdentifier": "m1"}]
        assert self.dte(pedido_id, turno_id)["estado"] == "fallido"
        tipos = [e["tipo"] for e in aws.almacen().listar("operacion", claves.eventos(L), consistente=True)]
        assert "dte.fallido" in tipos

    def test_reenvio_desde_fallidos_vuelve_a_intentar(self, nube, monkeypatch):
        monkeypatch.setenv("DTE_MODO", "error5xx")
        monkeypatch.setattr(aws, "cambiar_visibilidad", lambda *a: None)
        funcion = cargar("emision-dte")
        pedido_id, turno_id = vender()
        funcion.lambda_handler(self.mensaje(pedido_id, turno_id, 5))
        assert self.dte(pedido_id, turno_id)["estado"] == "fallido"
        monkeypatch.setenv("DTE_MODO", "ok")  # proveedor recuperado; el mensaje vuelve por redrive
        assert cargar("emision-dte").lambda_handler(self.mensaje(pedido_id, turno_id, 1)) == {"batchItemFailures": []}
        dte = self.dte(pedido_id, turno_id)
        assert (dte["estado"], dte["folio"]) == ("emitido", 1)

    def test_modo_lento_emite(self, nube, monkeypatch):
        monkeypatch.setenv("DTE_MODO", "lento")
        monkeypatch.setenv("DTE_LATENCIA_MS", "1")
        funcion = cargar("emision-dte")
        pedido_id, turno_id = vender()
        funcion.lambda_handler(self.mensaje(pedido_id, turno_id))
        assert self.dte(pedido_id, turno_id)["estado"] == "emitido"


@pytest.fixture
def dynamo_impresora_caja(nube):
    nube.dynamo.put_item(TableName="configuracion", Item={
        "PK": {"S": L}, "SK": {"S": "IMPRESORA#imp_caja"}, "impresora_id": {"S": "imp_caja"},
        "nombre": {"S": "Caja"}, "activa": {"BOOL": True}, "version": {"N": "1"}})


class TestDrenador:
    def mensaje(self, operacion, cuerpo, *, sub="garzon1", command_id=None, ocurrido=None):
        return {"messageId": ids.nuevo_ulid(), "body": json.dumps({
            "v": 1, "operacion": operacion, "local_id": LOCAL, "grupo": f"{LOCAL}#m1", "cuerpo": cuerpo,
            "command_id": command_id or ids.nuevo_ulid(), "sub": sub, "email": f"{sub}@demo.cl", "nombre": sub,
            "ocurrido_en": ocurrido or tiempo.iso(tiempo.ahora_utc()), "entrada": "servidor"})}

    def test_reaplica_en_orden_con_ids_del_cliente_y_retiene_la_impresion(self, nube):
        drenador = cargar("drenador-contingencia")
        pedido_id, item_id = ids.nuevo_ulid(), ids.nuevo_ulid()
        hace_10_min = tiempo.iso(tiempo.ahora_utc() - timedelta(minutes=10))
        lote = {"Records": [
            self.mensaje("pedido.abrir", {"mesa_id": "m1", "pedido_id": pedido_id}, ocurrido=hace_10_min),
            self.mensaje("pedido.agregar_item", {"mesa_id": "m1", "pedido_id": pedido_id, "item_id": item_id,
                                                 "producto_id": "pizza"}),
            self.mensaje("pedido.enviar_tanda", {"mesa_id": "m1", "pedido_id": pedido_id}),
        ]}
        assert drenador.lambda_handler(lote) == {"batchItemFailures": []}
        pedido = aws.almacen().pedido(L, pedido_id)
        assert (pedido.origen, pedido.creado_en, pedido.item(item_id).estado) == ("contingencia", hace_10_min, "enviado")
        assert len(aws.almacen().listar("operacion", claves.retenidos(L), "RET#")) == 1
        assert aws.almacen().listar("operacion", claves.impresora(L, "imp_cocina"), "PEND#") == []

    def test_comando_ya_aplicado_no_se_duplica(self, nube):
        drenador = cargar("drenador-contingencia")
        comando = ids.nuevo_ulid()
        pedido_id = ejecutar(aws.almacen(), P.ABRIR, ctx(command_id=comando), {"mesa_id": "m1"}).cuerpo["pedido_id"]
        drenador.lambda_handler({"Records": [self.mensaje("pedido.abrir", {"mesa_id": "m1"}, command_id=comando)]})
        assert aws.almacen().mesa_estado(L, "m1").pedido_id == pedido_id
        assert aws.almacen().listar("operacion", claves.conflictos(L)) == []

    def test_rechazo_al_reaplicar_genera_conflicto_y_no_se_reintenta(self, nube):
        drenador = cargar("drenador-contingencia")
        pedido_id, _ = vender()  # la mesa ya se cerró
        resultado = drenador.lambda_handler({"Records": [
            self.mensaje("pedido.agregar_item", {"mesa_id": "m1", "pedido_id": pedido_id, "producto_id": "pizza"})]})
        assert resultado == {"batchItemFailures": []}
        conflictos = aws.almacen().listar("operacion", claves.conflictos(L), consistente=True)
        assert len(conflictos) == 1 and conflictos[0]["codigo_rechazo"] == "PEDIDO_CERRADO"
        tipos = [e["tipo"] for e in aws.almacen().listar("operacion", claves.eventos(L), consistente=True)]
        assert "conflicto.registrado" in tipos

    def test_persona_sin_acceso_genera_conflicto(self, nube):
        drenador = cargar("drenador-contingencia")
        nube.dynamo.update_item(TableName="configuracion",
                                Key={"PK": {"S": "USER#garzon1"}, "SK": {"S": claves.sk_membresia(TENANT, LOCAL)}},
                                UpdateExpression="SET #e = :a", ExpressionAttributeNames={"#e": "estado"},
                                ExpressionAttributeValues={":a": {"S": "archivado"}})
        drenador.lambda_handler({"Records": [self.mensaje("pedido.abrir", {"mesa_id": "m1"})]})
        conflictos = aws.almacen().listar("operacion", claves.conflictos(L), consistente=True)
        assert conflictos[0]["codigo_rechazo"] == "SIN_ACCESO_AL_LOCAL"

    def test_falla_de_infraestructura_devuelve_el_mensaje_y_los_siguientes(self, nube, monkeypatch):
        drenador = cargar("drenador-contingencia")
        monkeypatch.setenv("SIMULAR_FALLA_DYNAMODB", "true")
        lote = {"Records": [self.mensaje("pedido.abrir", {"mesa_id": "m1"}),
                            self.mensaje("pedido.abrir", {"mesa_id": "m2"})]}
        resultado = drenador.lambda_handler(lote)
        assert [f["itemIdentifier"] for f in resultado["batchItemFailures"]] == [r["messageId"] for r in lote["Records"]]


class TestTareasProgramadas:
    def test_reencola_documentos_atascados_y_avisa_turno_largo_una_vez(self, nube, monkeypatch):
        monkeypatch.setenv("MINUTOS_DTE", "0")
        monkeypatch.setenv("HORAS_TURNO", "0")
        publicados = []
        monkeypatch.setattr(aws, "publicar", lambda tema, asunto, mensaje, **_: publicados.append(asunto))
        tareas = cargar("tareas-programadas")
        pedido_id, turno_id = vender()
        resultado = tareas.lambda_handler()
        assert resultado["dte_reencolados"] == 1 and resultado["turnos_avisados"] == 1
        assert [json.loads(m["Body"])["venta_id"] for m in mensajes(nube, nube.cola_dte)] == [pedido_id]
        assert tareas.lambda_handler()["turnos_avisados"] == 0
        assert publicados.count("MISE: turno de caja abierto hace demasiado tiempo") == 1

    def test_avisa_impresion_atascada(self, nube, monkeypatch):
        monkeypatch.setenv("MINUTOS_IMPRESION", "0")
        publicados = []
        monkeypatch.setattr(aws, "publicar", lambda tema, asunto, mensaje, **_: publicados.append(asunto))
        tareas = cargar("tareas-programadas")
        almacen = aws.almacen()
        pedido_id = ejecutar(almacen, P.ABRIR, ctx(), {"mesa_id": "m1"}).cuerpo["pedido_id"]
        ejecutar(almacen, P.AGREGAR_ITEM, ctx(), {"pedido_id": pedido_id, "producto_id": "pizza"})
        ejecutar(almacen, P.ENVIAR_TANDA, ctx(), {"pedido_id": pedido_id})
        assert tareas.lambda_handler()["impresiones_avisadas"] == 1
        assert publicados == ["MISE: impresora sin retirar trabajos"]
