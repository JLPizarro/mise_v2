"""Función `mensajeria` con SNS y SQS simulados: destinos, reglas de distribución, mensajes de prueba
que llegan solo al consumidor previsto, idempotencia, permisos y mensajes fallidos."""

import json

import pytest

from pos_dominio import claves, ids, tiempo
from pos_dominio.dte import ErrorProveedor
from pos_dominio.infra import fallos

from funciones.utiles import cargar, cuerpo, evento
from integracion.semilla import L, LOCAL, TENANT

B = "/locales/{local_id}/mensajeria"
P = {"local_id": LOCAL}


@pytest.fixture
def mensajeria(nube):
    return cargar("mensajeria").lambda_handler


def llamar(funcion, ruta, parametros=None, datos=None, sub="admin1", command_id="auto"):
    return funcion(evento(ruta, {**P, **(parametros or {})}, datos, sub=sub, command_id=command_id))


def crear(funcion, **datos):
    base = {"nombre": "Contabilidad", "tipo": "cola", "avisos": ["documento_rechazado"]}
    return llamar(funcion, f"POST {B}/destinos", datos=base | datos)


def mensajes_de(nube, nombre_cola):
    url = nube.sqs.get_queue_url(QueueName=nombre_cola)["QueueUrl"]
    return nube.sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, MessageAttributeNames=["All"]).get("Messages", [])


def suscripciones(nube):
    tema = nube.sns.list_topics()["Topics"]
    arn = next(t["TopicArn"] for t in tema if t["TopicArn"].endswith(":pos-avisos-dueno"))
    return nube.sns.list_subscriptions_by_topic(TopicArn=arn)["Subscriptions"]


class TestDestinosYReglas:
    def test_crear_destino_cola_con_su_regla(self, nube, mensajeria):
        r = crear(mensajeria)
        assert r["statusCode"] == 201, r["body"]
        d = cuerpo(r)
        assert d["tipo"] == "cola" and d["avisos"] == ["documento_rechazado"] and d["estado"] == "activa"
        assert d["cola"].startswith("pos-destino-")
        [sub] = suscripciones(nube)
        assert sub["Protocol"] == "sqs"
        filtro = json.loads(nube.sns.get_subscription_attributes(SubscriptionArn=sub["SubscriptionArn"])["Attributes"]["FilterPolicy"])
        assert filtro == {"aviso": ["documento_rechazado"], "tenant_id": [TENANT], "local_id": [LOCAL]}
        listado = cuerpo(llamar(mensajeria, f"GET {B}/destinos"))
        assert [x["nombre"] for x in listado["destinos"]] == ["Contabilidad"] and listado["limite"] == 10

    def test_crear_destino_correo(self, nube, mensajeria):
        r = crear(mensajeria, nombre="Jefe de turno", tipo="correo", correo="Jefe@Demo.cl")
        assert r["statusCode"] == 201, r["body"]
        assert cuerpo(r)["correo"] == "jefe@demo.cl"
        assert suscripciones(nube)[0]["Protocol"] == "email"

    def test_el_mensaje_de_prueba_llega_solo_al_destino_con_la_regla(self, nube, mensajeria):
        contabilidad = cuerpo(crear(mensajeria))
        caja = cuerpo(crear(mensajeria, nombre="Caja central", avisos=["comanda_en_conflicto"]))
        r = llamar(mensajeria, f"POST {B}/pruebas", datos={"aviso": "documento_rechazado"})
        assert r["statusCode"] == 200, r["body"]
        assert [d["nombre"] for d in cuerpo(r)["destinos_esperados"]] == ["Contabilidad"]
        [recibido] = mensajes_de(nube, contabilidad["cola"])
        assert "prueba" in recibido["Body"].lower()
        assert mensajes_de(nube, caja["cola"]) == []

    def test_un_aviso_real_del_procesador_sigue_las_mismas_reglas(self, nube, mensajeria):
        destino = cuerpo(crear(mensajeria))
        procesador = cargar("procesador-eventos")
        procesador.procesar({"event_id": ids.nuevo_ulid(), "tipo": "dte.rechazado", "v": 1, "tenant_id": TENANT,
                             "local_id": LOCAL, "ocurrido_en": tiempo.iso(tiempo.ahora_utc()),
                             "datos": {"venta_id": "venta-1", "folio": 7, "motivo": "RUT del receptor inválido"}})
        [recibido] = mensajes_de(nube, destino["cola"])
        assert "venta-1" in recibido["Body"] and "RUT del receptor" in recibido["Body"]

    def test_agregar_y_quitar_reglas_cambia_el_filtro(self, nube, mensajeria):
        d = cuerpo(crear(mensajeria))
        r = llamar(mensajeria, f"POST {B}/destinos/{{destino_id}}/reglas", {"destino_id": d["destino_id"]},
                   {"aviso": "comanda_en_conflicto"})
        assert r["statusCode"] == 201 and cuerpo(r)["avisos"] == ["documento_rechazado", "comanda_en_conflicto"]
        llamar(mensajeria, f"POST {B}/pruebas", datos={"aviso": "comanda_en_conflicto"})
        assert len(mensajes_de(nube, d["cola"])) == 1
        repetida = llamar(mensajeria, f"POST {B}/destinos/{{destino_id}}/reglas", {"destino_id": d["destino_id"]},
                          {"aviso": "comanda_en_conflicto"})
        assert (repetida["statusCode"], cuerpo(repetida)["codigo"]) == (409, "REGLA_EXISTENTE")

        r = llamar(mensajeria, f"DELETE {B}/destinos/{{destino_id}}/reglas/{{aviso}}",
                   {"destino_id": d["destino_id"], "aviso": "documento_rechazado"})
        assert r["statusCode"] == 200 and cuerpo(r)["avisos"] == ["comanda_en_conflicto"]
        ultima = llamar(mensajeria, f"DELETE {B}/destinos/{{destino_id}}/reglas/{{aviso}}",
                        {"destino_id": d["destino_id"], "aviso": "comanda_en_conflicto"})
        assert (ultima["statusCode"], cuerpo(ultima)["codigo"]) == (409, "ULTIMA_REGLA")
        inexistente = llamar(mensajeria, f"DELETE {B}/destinos/{{destino_id}}/reglas/{{aviso}}",
                             {"destino_id": d["destino_id"], "aviso": "cierre_con_diferencia"})
        assert (inexistente["statusCode"], cuerpo(inexistente)["codigo"]) == (404, "REGLA_NO_ENCONTRADA")

    def test_eliminar_destino_quita_suscripcion_cola_y_registro(self, nube, mensajeria):
        d = cuerpo(crear(mensajeria))
        r = llamar(mensajeria, f"DELETE {B}/destinos/{{destino_id}}", {"destino_id": d["destino_id"]})
        assert r["statusCode"] == 200, r["body"]
        assert suscripciones(nube) == []
        assert not any(d["cola"] in u for u in nube.sqs.list_queues().get("QueueUrls", []))
        assert cuerpo(llamar(mensajeria, f"GET {B}/destinos"))["destinos"] == []
        # Con el nombre liberado se puede volver a crear.
        assert crear(mensajeria)["statusCode"] == 201

    def test_ver_mensajes_de_un_destino_cola(self, nube, mensajeria):
        d = cuerpo(crear(mensajeria))
        llamar(mensajeria, f"POST {B}/pruebas", datos={"aviso": "documento_rechazado"})
        r = llamar(mensajeria, f"GET {B}/destinos/{{destino_id}}/mensajes", {"destino_id": d["destino_id"]})
        assert r["statusCode"] == 200 and len(cuerpo(r)["mensajes"]) == 1
        # Mirar no consume: el mensaje sigue en la cola.
        assert len(mensajes_de(nube, d["cola"])) == 1


class TestValidacionYPermisos:
    @pytest.mark.parametrize("datos, codigo", [
        ({"nombre": ""}, "NOMBRE_INVALIDO"),
        ({"tipo": "sms"}, "TIPO_DESTINO_INVALIDO"),
        ({"tipo": "correo", "correo": "x"}, "CORREO_INVALIDO"),
        ({"avisos": []}, "REGLAS_REQUERIDAS"),
        ({"avisos": ["documento_fallido"]}, "AVISO_NO_ADMINISTRABLE"),
        ({"avisos": ["inventado"]}, "AVISO_DESCONOCIDO"),
        ({"prioridad": "alta"}, "CAMPO_DESCONOCIDO"),
    ])
    def test_solicitud_invalida_no_crea_nada(self, nube, mensajeria, datos, codigo):
        r = crear(mensajeria, **datos)
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (422, codigo)
        assert "campo" in cuerpo(r)["detalle"]
        assert suscripciones(nube) == []

    def test_nombre_y_correo_duplicados(self, nube, mensajeria):
        crear(mensajeria, nombre="Jefe", tipo="correo", correo="jefe@demo.cl")
        r = crear(mensajeria, nombre="  jefe ", avisos=["comanda_en_conflicto"])
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (409, "DESTINO_DUPLICADO")
        r = crear(mensajeria, nombre="Otro", tipo="correo", correo="JEFE@demo.cl")
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (409, "CORREO_YA_REGISTRADO")

    def test_limite_de_destinos(self, nube, mensajeria):
        for i in range(10):
            assert crear(mensajeria, nombre=f"Destino {i}")["statusCode"] == 201
        r = crear(mensajeria, nombre="Uno más")
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (409, "LIMITE_DE_DESTINOS")

    def test_cajero_y_garzon_no_administran_la_mensajeria(self, nube, mensajeria):
        for sub in ("cajero1", "garzon1"):
            r = llamar(mensajeria, f"GET {B}/destinos", sub=sub)
            assert (r["statusCode"], cuerpo(r)["codigo"]) == (403, "ROL_NO_PERMITIDO")

    def test_mismo_comando_no_duplica_recursos(self, nube, mensajeria):
        comando = ids.nuevo_ulid()
        datos = {"nombre": "Contabilidad", "tipo": "cola", "avisos": ["documento_rechazado"]}
        primera = llamar(mensajeria, f"POST {B}/destinos", datos=datos, command_id=comando)
        segunda = llamar(mensajeria, f"POST {B}/destinos", datos=datos, command_id=comando)
        assert primera["statusCode"] == segunda["statusCode"] == 201
        assert segunda["headers"].get("x-comando-repetido") == "true"
        assert len(suscripciones(nube)) == 1
        otra = llamar(mensajeria, f"POST {B}/destinos", datos={**datos, "nombre": "Otro"}, command_id=comando)
        assert cuerpo(otra)["codigo"] == "COMANDO_REUTILIZADO"

    def test_el_catalogo_muestra_canales_rutas_y_estado(self, nube, mensajeria):
        datos = cuerpo(llamar(mensajeria, f"GET {B}/canales"))
        canales = {c["id"]: c for c in datos["canales"]}
        assert canales["dte-emision"]["estado"] == {"visibles": 0, "en_proceso": 0}
        assert canales["dte-emision"]["fallidos"] == "dte-emision-fallidos" and canales["avisos"]["protegido"]
        assert any(r["evento"] == "venta.cerrada" and r["consumidor"] == "emision-dte" for r in datos["rutas"])
        assert {a["id"] for a in datos["avisos"] if a["administrable"]} == {
            "cierre_con_diferencia", "documento_rechazado", "comanda_en_conflicto", "autorizacion_bloqueada",
            "turno_abierto_demasiado"}


class TestFallidos:
    def poner_fallido(self, nube, cola, cuerpo_mensaje, **extra):
        url = nube.sqs.get_queue_url(QueueName=cola)["QueueUrl"]
        return nube.sqs.send_message(QueueUrl=url, MessageBody=json.dumps(cuerpo_mensaje), **extra)["MessageId"]

    def test_lista_solo_los_del_local_con_su_diagnostico(self, nube, mensajeria):
        propio = self.poner_fallido(nube, "dte-emision-fallidos", {"tenant_id": TENANT, "local_id": LOCAL,
                                                                   "turno_id": "t1", "venta_id": "venta-9"})
        self.poner_fallido(nube, "dte-emision-fallidos", {"tenant_id": "otro", "local_id": "otro_local",
                                                          "turno_id": "t1", "venta_id": "ajena"})
        fallos.registrar(consumidor="emision-dte", canal="dte-emision", mensaje_id=propio, intento=5,
                         error=ErrorProveedor("error5xx"), mensaje="Proveedor no disponible (error5xx)",
                         tenant_id=TENANT, local_id=LOCAL,
                         referencia="venta venta-9", recuperable=False)
        r = llamar(mensajeria, f"GET {B}/fallidos")
        assert r["statusCode"] == 200, r["body"]
        [f] = cuerpo(r)["fallidos"]
        assert f["mensaje_id"] == propio and f["canal"] == "dte-emision" and "venta-9" in f["resumen"]
        assert f["diagnostico"]["error_mensaje"] == "Proveedor no disponible (error5xx)" and f["diagnostico"]["intento"] == 5
        assert f["diagnostico"]["origen"] == "proveedor" and f["diagnostico"]["error_tipo"] == "ErrorProveedor"
        assert cuerpo(r)["errores_recientes"][0]["consumidor"] == "emision-dte"

    def test_reprocesar_devuelve_el_mensaje_a_su_cola(self, nube, mensajeria):
        mid = self.poner_fallido(nube, "dte-emision-fallidos", {"tenant_id": TENANT, "local_id": LOCAL,
                                                                "turno_id": "t1", "venta_id": "venta-9"})
        r = llamar(mensajeria, f"POST {B}/fallidos/{{mensaje_id}}/reprocesar", {"mensaje_id": mid}, {"canal": "dte-emision"})
        assert r["statusCode"] == 200 and cuerpo(r)["estado"] == "reenviado", r["body"]
        [reenviado] = mensajes_de(nube, "dte-emision")
        assert json.loads(reenviado["Body"])["venta_id"] == "venta-9"
        assert mensajes_de(nube, "dte-emision-fallidos") == []

    def test_reprocesar_contingencia_conserva_el_grupo_fifo(self, nube, mensajeria):
        mensaje = {"v": 1, "operacion": "pedido.abrir", "local_id": LOCAL, "grupo": f"{LOCAL}#m1",
                   "cuerpo": {"mesa_id": "m1"}, "command_id": ids.nuevo_ulid(), "sub": "garzon1", "nombre": "Garzón"}
        mid = self.poner_fallido(nube, "contingencia-comandas-fallidos.fifo", mensaje, MessageGroupId=mensaje["grupo"],
                                 MessageDeduplicationId=mensaje["command_id"])
        r = llamar(mensajeria, f"POST {B}/fallidos/{{mensaje_id}}/reprocesar", {"mensaje_id": mid},
                   {"canal": "contingencia-comandas"})
        assert r["statusCode"] == 200, r["body"]
        url = nube.sqs.get_queue_url(QueueName="contingencia-comandas.fifo")["QueueUrl"]
        [m] = nube.sqs.receive_message(QueueUrl=url, AttributeNames=["All"])["Messages"]
        assert m["Attributes"]["MessageGroupId"] == f"{LOCAL}#m1"

    def test_descartar_y_validaciones(self, nube, mensajeria):
        mid = self.poner_fallido(nube, "dte-emision-fallidos", {"tenant_id": TENANT, "local_id": LOCAL,
                                                                "turno_id": "t1", "venta_id": "v"})
        malo = llamar(mensajeria, f"POST {B}/fallidos/{{mensaje_id}}/descartar", {"mensaje_id": mid}, {"canal": "avisos"})
        assert (malo["statusCode"], cuerpo(malo)["codigo"]) == (422, "CANAL_INVALIDO")
        r = llamar(mensajeria, f"POST {B}/fallidos/{{mensaje_id}}/descartar", {"mensaje_id": mid}, {"canal": "dte-emision"})
        assert r["statusCode"] == 200 and cuerpo(r)["estado"] == "descartado"
        assert mensajes_de(nube, "dte-emision-fallidos") == []
        otra = llamar(mensajeria, f"POST {B}/fallidos/{{mensaje_id}}/descartar", {"mensaje_id": mid}, {"canal": "dte-emision"})
        assert (otra["statusCode"], cuerpo(otra)["codigo"]) == (404, "MENSAJE_NO_ENCONTRADO")

    def test_no_se_puede_tocar_un_fallido_de_otro_local(self, nube, mensajeria):
        mid = self.poner_fallido(nube, "dte-emision-fallidos", {"tenant_id": "otro", "local_id": "x",
                                                                "turno_id": "t", "venta_id": "v"})
        r = llamar(mensajeria, f"POST {B}/fallidos/{{mensaje_id}}/descartar", {"mensaje_id": mid}, {"canal": "dte-emision"})
        assert r["statusCode"] == 404
        assert len(mensajes_de(nube, "dte-emision-fallidos")) == 1


class TestRegistroDeFallos:
    """Cada fallo queda con su origen: proveedor externo, AWS propio, negocio o defecto de código."""

    def emitir(self, cuerpo_mensaje, recepcion=2):
        cargar("emision-dte").lambda_handler({"Records": [{
            "messageId": "msg-1", "receiptHandle": "r", "attributes": {"ApproximateReceiveCount": str(recepcion)},
            "body": json.dumps(cuerpo_mensaje)}]})

    def fallos_del_local(self, nube):
        return nube.dynamo.query(TableName="operacion", KeyConditionExpression="PK = :pk",
                                 ExpressionAttributeValues={":pk": {"S": claves.fallos(L)}})["Items"]

    def test_proveedor_caido(self, nube, monkeypatch):
        from funciones.test_asincronas import vender

        monkeypatch.setenv("DTE_MODO", "error5xx")
        pedido_id, turno_id = vender()
        self.emitir({"tenant_id": TENANT, "local_id": LOCAL, "turno_id": turno_id, "venta_id": pedido_id})
        [fila] = self.fallos_del_local(nube)
        assert fila["origen"]["S"] == "proveedor" and fila["error_tipo"]["S"] == "ErrorProveedor"
        assert fila["consumidor"]["S"] == "emision-dte" and fila["mensaje_id"]["S"] == "msg-1"
        assert fila["intento"]["N"] == "2" and "error5xx" in fila["error_mensaje"]["S"]

    def test_falla_de_aws_propio(self, nube, monkeypatch):
        from funciones.test_asincronas import vender

        pedido_id, turno_id = vender()
        monkeypatch.setenv("SIMULAR_FALLA_DYNAMODB", "true")  # DynamoDB «caído» para el consumidor
        self.emitir({"tenant_id": TENANT, "local_id": LOCAL, "turno_id": turno_id, "venta_id": pedido_id})
        [fila] = self.fallos_del_local(nube)
        assert fila["origen"]["S"] == "aws" and fila["error_tipo"]["S"] == "ErrorInfraestructura"

    def test_defecto_de_codigo(self, nube):
        self.emitir({"tenant_id": TENANT, "local_id": LOCAL})  # mensaje sin turno ni venta
        [fila] = self.fallos_del_local(nube)
        assert fila["origen"]["S"] == "codigo" and fila["error_tipo"]["S"] == "KeyError"

    def test_clasificacion(self):
        from botocore.exceptions import ClientError
        from pos_dominio.errores import Conflicto, ErrorDeCodigo, ErrorInfraestructura

        assert fallos.clasificar(ErrorProveedor("timeout")) == "proveedor"
        assert fallos.clasificar(ErrorInfraestructura("x")) == "aws"
        assert fallos.clasificar(ClientError({"Error": {"Code": "ThrottlingException"}}, "Query")) == "aws"
        assert fallos.clasificar(Conflicto("mesa cobrada")) == "negocio"
        assert fallos.clasificar(ErrorDeCodigo("x")) == "codigo"
        assert fallos.clasificar(KeyError("venta_id")) == "codigo"
