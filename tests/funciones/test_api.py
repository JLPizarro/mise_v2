"""Funciones de la API de punta a punta: evento del API Gateway (formato 2.0) -> respuesta HTTP."""

import base64
import hashlib
import hmac
import json

import pytest

from pos_dominio import ids

from funciones.utiles import cargar, cuerpo, evento

L_ID = "local_01"


@pytest.fixture
def salon(nube):
    return cargar("salon").lambda_handler


@pytest.fixture
def pedidos(nube):
    return cargar("pedidos").lambda_handler


@pytest.fixture
def caja(nube):
    return cargar("caja").lambda_handler


@pytest.fixture
def admin(nube):
    return cargar("administracion").lambda_handler


def abrir_mesa(pedidos, mesa="m1", sub="garzon1"):
    r = pedidos(evento("POST /locales/{local_id}/pedidos", {"local_id": L_ID}, {"mesa_id": mesa}, sub=sub))
    assert r["statusCode"] in (200, 201), r
    return cuerpo(r)["pedido_id"]


class TestFormatoYSeguridad:
    def test_salud_sin_autenticacion(self, salon):
        r = salon(evento("GET /salud", sub=None))
        assert r["statusCode"] == 200 and cuerpo(r)["dynamodb"] == "ok"

    def test_salud_responde_503_si_dynamodb_falla(self, salon, monkeypatch):
        monkeypatch.setenv("SIMULAR_FALLA_DYNAMODB", "true")
        r = salon(evento("GET /salud", sub=None))
        assert r["statusCode"] == 503 and cuerpo(r)["codigo"] == "SERVICIO_NO_DISPONIBLE"

    def test_error_con_formato_unico(self, salon):
        r = salon(evento("GET /locales/{local_id}/salon", {"local_id": "otro_local"}))
        assert r["statusCode"] == 403
        assert set(cuerpo(r)) >= {"codigo", "mensaje", "requestId"}
        assert cuerpo(r)["requestId"].startswith("req-")

    def test_usuario_inexistente_con_token_valido_es_403(self, salon):
        r = salon(evento("GET /yo", sub="desconocido"))
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (403, "USUARIO_NO_REGISTRADO")

    def test_email_no_verificado_es_403(self, salon):
        r = salon(evento("GET /yo", claims_extra={"email_verified": "false"}))
        assert cuerpo(r)["codigo"] == "EMAIL_NO_VERIFICADO"

    def test_escritura_sin_x_command_id_se_rechaza(self, pedidos):
        r = pedidos(evento("POST /locales/{local_id}/pedidos", {"local_id": L_ID}, {"mesa_id": "m1"}, command_id=None))
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (422, "COMMAND_ID_INVALIDO")

    def test_cuerpo_en_base64(self, pedidos):
        r = pedidos(evento("POST /locales/{local_id}/pedidos", {"local_id": L_ID}, {"mesa_id": "m1"}, en_base64=True))
        assert r["statusCode"] == 201

    def test_json_invalido_es_400(self, pedidos):
        r = pedidos(evento("POST /locales/{local_id}/pedidos", {"local_id": L_ID}, "{no es json"))
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (400, "JSON_INVALIDO")

    def test_monto_con_decimales_no_se_redondea(self, pedidos):
        pedido_id = abrir_mesa(pedidos)
        r = pedidos(evento("POST /locales/{local_id}/pedidos/{pedido_id}/items",
                           {"local_id": L_ID, "pedido_id": pedido_id}, '{"producto_id":"pizza","cantidad":1.5}'))
        assert r["statusCode"] == 422

    def test_la_ruta_manda_sobre_el_cuerpo(self, pedidos):
        propio = abrir_mesa(pedidos, "m1")
        ajeno = abrir_mesa(pedidos, "m2")
        r = pedidos(evento("POST /locales/{local_id}/pedidos/{pedido_id}/items", {"local_id": L_ID, "pedido_id": propio},
                           {"producto_id": "pizza", "pedido_id": ajeno}))
        assert cuerpo(r)["item_id"] and r["statusCode"] == 201
        ver = pedidos(evento("GET /locales/{local_id}/pedidos/{pedido_id}", {"local_id": L_ID, "pedido_id": ajeno}))
        assert cuerpo(ver)["items"] == []

    def test_mismo_command_id_responde_igual_y_lo_marca(self, pedidos):
        pedido_id = abrir_mesa(pedidos)
        comando = ids.nuevo_ulid()
        args = ("POST /locales/{local_id}/pedidos/{pedido_id}/items", {"local_id": L_ID, "pedido_id": pedido_id},
                {"producto_id": "pizza"})
        r1, r2 = pedidos(evento(*args, command_id=comando)), pedidos(evento(*args, command_id=comando))
        assert cuerpo(r1) == cuerpo(r2) and r2["headers"].get("x-comando-repetido") == "true"

    def test_el_log_no_contiene_el_token_ni_el_codigo(self, caja, capsys, monkeypatch):
        import logging
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        logging.getLogger().handlers = [logging.StreamHandler()]
        caja(evento("POST /locales/{local_id}/caja/retiros", {"local_id": L_ID},
                    {"monto": 1000, "motivo": "x", "autorizador_id": "admin1", "codigo": "9876"}, sub="cajero1",
                    encabezados={"authorization": "Bearer eyJ.secreto.firma"}))
        salida = capsys.readouterr().err
        assert "eyJ.secreto" not in salida and "9876" not in salida


class TestSalon:
    def test_yo_lista_los_locales_con_rol(self, salon):
        r = cuerpo(salon(evento("GET /yo", sub="cajero1")))
        assert r["locales"][0] | {} and r["locales"][0]["rol"] == "cajero"
        assert r["locales"][0]["nombre_local"] == "Local Demo"

    def test_plano_une_estructura_y_estado(self, salon, pedidos):
        pedido_id = abrir_mesa(pedidos)
        plano = cuerpo(salon(evento("GET /locales/{local_id}/salon", {"local_id": L_ID})))
        m1 = next(m for m in plano["mesas"] if m["mesa_id"] == "m1")
        assert (m1["estado"], m1["pedido_id"], m1["numero"]) == ("ocupada", pedido_id, 1)
        assert next(m for m in plano["mesas"] if m["mesa_id"] == "m2")["estado"] == "libre"

    def test_catalogo_sin_cambios_no_reenvia_productos(self, salon):
        r = cuerpo(salon(evento("GET /locales/{local_id}/catalogo", {"local_id": L_ID})))
        assert len(r["productos"]) == 3
        r2 = cuerpo(salon(evento("GET /locales/{local_id}/catalogo", {"local_id": L_ID}, query={"version": str(r["version"])})))
        assert r2 == {"version": r["version"], "sin_cambios": True}

    def test_garzon_no_bloquea_mesas(self, salon):
        r = salon(evento("POST /locales/{local_id}/mesas/{mesa_id}/bloqueo", {"local_id": L_ID, "mesa_id": "m3"},
                         {"bloqueada": True}))
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (403, "ROL_NO_PERMITIDO")

    def test_cajero_bloquea_y_la_mesa_no_recibe_pedidos(self, salon, pedidos):
        salon(evento("POST /locales/{local_id}/mesas/{mesa_id}/bloqueo", {"local_id": L_ID, "mesa_id": "m3"},
                     {"bloqueada": True}, sub="cajero1"))
        r = pedidos(evento("POST /locales/{local_id}/pedidos", {"local_id": L_ID}, {"mesa_id": "m3"}))
        assert cuerpo(r)["codigo"] == "MESA_BLOQUEADA"


class TestContingenciaDesdePedidos:
    def test_falla_de_dynamodb_encola_y_responde_202(self, nube, pedidos, monkeypatch):
        monkeypatch.setenv("SIMULAR_FALLA_DYNAMODB", "true")
        comando = ids.nuevo_ulid()
        pedido_id = ids.nuevo_ulid()
        r = pedidos(evento("POST /locales/{local_id}/pedidos", {"local_id": L_ID},
                           {"mesa_id": "m1", "pedido_id": pedido_id}, command_id=comando))
        assert (r["statusCode"], cuerpo(r)["estado"]) == (202, "aceptada_en_contingencia")
        mensajes = nube.sqs.receive_message(QueueUrl=nube.cola_contingencia, AttributeNames=["All"],
                                            MaxNumberOfMessages=10)["Messages"]
        assert len(mensajes) == 1
        mensaje = json.loads(mensajes[0]["Body"])
        assert (mensaje["operacion"], mensaje["command_id"], mensaje["grupo"]) == ("pedido.abrir", comando, f"{L_ID}#m1")
        assert mensajes[0]["Attributes"]["MessageGroupId"] == f"{L_ID}#m1"
        assert mensajes[0]["Attributes"]["MessageDeduplicationId"] == comando

    def test_rechazo_de_negocio_nunca_va_a_contingencia(self, nube, pedidos):
        r = pedidos(evento("POST /locales/{local_id}/pedidos", {"local_id": L_ID}, {"mesa_id": "no_existe"}))
        assert r["statusCode"] == 404
        assert "Messages" not in nube.sqs.receive_message(QueueUrl=nube.cola_contingencia)


class TestCaja:
    def flujo(self, pedidos, caja):
        caja(evento("POST /locales/{local_id}/caja/turnos", {"local_id": L_ID}, {"monto_apertura": 10_000}, sub="cajero1"))
        pedido_id = abrir_mesa(pedidos)
        pedidos(evento("POST /locales/{local_id}/pedidos/{pedido_id}/items", {"local_id": L_ID, "pedido_id": pedido_id},
                       {"producto_id": "pizza"}))
        pedidos(evento("POST /locales/{local_id}/pedidos/{pedido_id}/precuenta", {"local_id": L_ID, "pedido_id": pedido_id}))
        return pedido_id

    def test_pendientes_pago_y_finalizar(self, pedidos, caja):
        pedido_id = self.flujo(pedidos, caja)
        pendientes = cuerpo(caja(evento("GET /locales/{local_id}/caja/pendientes", {"local_id": L_ID}, sub="cajero1")))
        assert [p["pedido"]["pedido_id"] for p in pendientes["pendientes"]] == [pedido_id]
        r = caja(evento("POST /locales/{local_id}/pedidos/{pedido_id}/pagos", {"local_id": L_ID, "pedido_id": pedido_id},
                        {"medios": [{"metodo": "efectivo", "monto": 8000, "propina": 800, "efectivo_recibido": 10_000}]},
                        sub="cajero1"))
        assert cuerpo(r)["pagos"][0]["vuelto"] == 1200
        r = caja(evento("POST /locales/{local_id}/pedidos/{pedido_id}/finalizar", {"local_id": L_ID, "pedido_id": pedido_id},
                        {"tipo_documento": "boleta"}, sub="cajero1"))
        assert cuerpo(r)["documento"] == {"tipo": "boleta", "estado": "pendiente"}
        doc = cuerpo(caja(evento("GET /locales/{local_id}/caja/documentos/{venta_id}",
                                 {"local_id": L_ID, "venta_id": pedido_id}, sub="cajero1")))
        assert doc["estado"] == "pendiente"

    def test_garzon_no_cobra(self, pedidos, caja):
        pedido_id = self.flujo(pedidos, caja)
        r = caja(evento("POST /locales/{local_id}/pedidos/{pedido_id}/pagos", {"local_id": L_ID, "pedido_id": pedido_id},
                        {"medios": [{"metodo": "transferencia", "monto": 8000}]}))
        assert r["statusCode"] == 403

    def test_turno_abierto_no_revela_totales(self, pedidos, caja):
        self.flujo(pedidos, caja)
        turno = cuerpo(caja(evento("GET /locales/{local_id}/caja/turno", {"local_id": L_ID}, sub="cajero1")))
        assert not any(k.startswith("tot_") for k in turno) and "resultado" not in turno

    def test_lista_de_autorizadores_solo_con_codigo(self, caja):
        r = cuerpo(caja(evento("GET /locales/{local_id}/caja/autorizadores", {"local_id": L_ID}, sub="cajero1")))
        assert sorted(a["sub"] for a in r["autorizadores"]) == ["admin1", "dueno1"]


class TestAdministracion:
    def test_crear_sector_y_mesa_duplicada_es_409(self, admin):
        r = admin(evento("POST /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "sectores"},
                         {"nombre": "Terraza"}, sub="admin1"))
        sector_id = cuerpo(r)["sector_id"]
        dup = admin(evento("POST /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "sectores"},
                           {"nombre": "  terraza "}, sub="admin1"))
        assert (dup["statusCode"], cuerpo(dup)["codigo"]) == (409, "DUPLICADO")
        crear_mesa = lambda: admin(evento("POST /locales/{local_id}/admin/{recurso}",  # noqa: E731
                                          {"local_id": L_ID, "recurso": "mesas"},
                                          {"sector_id": sector_id, "numero": 10}, sub="admin1"))
        assert crear_mesa()["statusCode"] == 201
        assert cuerpo(crear_mesa())["codigo"] == "DUPLICADO"

    def test_producto_con_modificadores_estables(self, admin):
        r = cuerpo(admin(evento("POST /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "productos"},
                                {"nombre": "Lomo", "categoria": "Fondos", "precio": 12000, "cuarto_id": "cocina",
                                 "modificadores": [{"nombre": "A punto"}]}, sub="admin1")))
        mod_id = r["modificadores"][0]["modificador_id"]
        r2 = cuerpo(admin(evento("PATCH /locales/{local_id}/admin/{recurso}/{id}",
                                 {"local_id": L_ID, "recurso": "productos", "id": r["producto_id"]},
                                 {"modificadores": [{"modificador_id": mod_id, "nombre": "A punto", "precio_adicional": 500},
                                                    {"nombre": "Bien cocido"}]}, sub="admin1")))
        assert r2["modificadores"][0]["modificador_id"] == mod_id and len(r2["modificadores"]) == 2

    def test_garzon_no_administra(self, admin):
        r = admin(evento("GET /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "productos"}))
        assert r["statusCode"] == 403

    def test_admin_no_puede_crear_duenos(self, admin):
        r = admin(evento("POST /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "personal"},
                         {"email": "nuevo@demo.cl", "nombre": "Nuevo", "rol": "dueno"}, sub="admin1"))
        assert r["statusCode"] == 403

    def test_invitacion_se_vincula_en_el_primer_ingreso(self, admin, salon):
        r = admin(evento("POST /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "personal"},
                         {"email": "Nueva.Garzona@demo.cl", "nombre": "Ana", "rol": "garzon"}, sub="admin1"))
        assert r["statusCode"] == 201
        yo = salon(evento("GET /yo", sub="google_123", claims_extra={"email": "nueva.garzona@demo.cl"}))
        assert cuerpo(yo)["locales"][0]["rol"] == "garzon"
        personal = cuerpo(admin(evento("GET /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "personal"},
                                       sub="admin1")))["personal"]
        ana = [p for p in personal if p["nombre"] == "Ana"]
        assert len(ana) == 1 and ana[0]["sub"] == "google_123" and not ana[0]["invitacion"]

    def test_archivar_quita_el_acceso(self, admin, salon, monkeypatch):
        from pos_dominio.infra import identidad
        admin(evento("PATCH /locales/{local_id}/admin/{recurso}/{id}", {"local_id": L_ID, "recurso": "personal", "id": "garzon1"},
                     {"estado": "archivado"}, sub="admin1"))
        identidad.limpiar_cache()  # en producción, hasta 60 s
        r = salon(evento("GET /locales/{local_id}/salon", {"local_id": L_ID}))
        assert (r["statusCode"], cuerpo(r)["codigo"]) == (403, "SIN_ACCESO_AL_LOCAL")

    def test_nadie_cambia_su_propio_rol(self, admin):
        r = admin(evento("PATCH /locales/{local_id}/admin/{recurso}/{id}", {"local_id": L_ID, "recurso": "personal", "id": "admin1"},
                         {"rol": "dueno"}, sub="admin1"))
        assert r["statusCode"] == 403

    def test_umbral_en_porcentaje_se_guarda_en_puntos_base(self, admin):
        r = admin(evento("PATCH /locales/{local_id}/admin/{recurso}/{id}",
                         {"local_id": L_ID, "recurso": "configuracion", "id": "local"},
                         '{"umbral_diferencia_pct": 2.5}', sub="admin1"))
        assert r["statusCode"] == 200, r
        assert (cuerpo(r)["umbral_diferencia_pb"], cuerpo(r)["umbral_diferencia_pct"]) == (250, 2.5)


class TestImpresion:
    def test_ciclo_cloudprnt(self, nube, admin, pedidos):
        impresora = cuerpo(admin(evento("POST /locales/{local_id}/admin/{recurso}", {"local_id": L_ID, "recurso": "impresoras"},
                                        {"nombre": "Cocina 2"}, sub="admin1")))
        admin(evento("PATCH /locales/{local_id}/admin/{recurso}/{id}", {"local_id": L_ID, "recurso": "cuartos", "id": "cocina"},
                     {"impresora_id": impresora["impresora_id"]}, sub="admin1"))
        pedido_id = abrir_mesa(pedidos)
        pedidos(evento("POST /locales/{local_id}/pedidos/{pedido_id}/items", {"local_id": L_ID, "pedido_id": pedido_id},
                       {"producto_id": "pizza", "observacion": "sin cebolla"}))
        pedidos(evento("POST /locales/{local_id}/pedidos/{pedido_id}/enviar", {"local_id": L_ID, "pedido_id": pedido_id}))

        imp = cargar("impresion").lambda_handler
        params = {"tenant_id": "demo", "local_id": L_ID, "impresora_id": impresora["impresora_id"]}
        basic = "Basic " + base64.b64encode(f"{impresora['impresora_id']}:{impresora['clave']}".encode()).decode()
        ruta = "/impresion/{tenant_id}/{local_id}/{impresora_id}"

        mala = imp(evento(f"POST {ruta}", params, {"status": "200 OK"}, sub=None, command_id=None,
                          encabezados={"authorization": "Basic " + base64.b64encode(b"x:y").decode()}))
        assert mala["statusCode"] == 401

        consulta = cuerpo(imp(evento(f"POST {ruta}", params, {"status": "200 OK"}, sub=None, command_id=None,
                                     encabezados={"authorization": basic})))
        assert consulta["jobReady"] is True
        token = consulta["jobToken"]
        trabajo = imp(evento(f"GET {ruta}", params, sub=None, query={"token": token, "type": "text/plain"},
                             encabezados={"authorization": basic}))
        assert trabajo["headers"]["content-type"].startswith("text/plain")
        assert "1 x Pizza" in trabajo["body"] and "sin cebolla" in trabajo["body"]
        fin = imp(evento(f"DELETE {ruta}", params, sub=None, command_id=None, query={"token": token, "code": "200 OK"},
                         encabezados={"authorization": basic}))
        assert cuerpo(fin) == {"confirmado": True, "estado": "impreso"}
        assert cuerpo(imp(evento(f"POST {ruta}", params, {}, sub=None, command_id=None,
                                 encabezados={"authorization": basic})))["jobReady"] is False


class TestOtrasRutas:
    def test_contingencia_encola_sin_tocar_dynamodb(self, nube, monkeypatch):
        monkeypatch.setenv("SIMULAR_FALLA_DYNAMODB", "true")
        funcion = cargar("contingencia").lambda_handler
        r = funcion(evento("POST /contingencia/comandas", None,
                           {"operacion": "pedido.agregar_item", "local_id": L_ID,
                            "cuerpo": {"pedido_id": ids.nuevo_ulid(), "mesa_id": "m1", "producto_id": "pizza"}}))
        assert r["statusCode"] == 202
        assert len(nube.sqs.receive_message(QueueUrl=nube.cola_contingencia)["Messages"]) == 1

    def test_contingencia_no_acepta_cobros(self, nube):
        funcion = cargar("contingencia").lambda_handler
        r = funcion(evento("POST /contingencia/comandas", None,
                           {"operacion": "caja.registrar_pago", "local_id": L_ID, "cuerpo": {"mesa_id": "m1"}}))
        assert r["statusCode"] == 422

    def test_reservas_resuelve_el_local_por_la_ruta(self, nube):
        funcion = cargar("reservas").lambda_handler
        r = funcion(evento("GET /publico/{tenant_id}/{local_id}/reservas/disponibilidad",
                           {"tenant_id": "demo", "local_id": L_ID}, sub=None))
        assert r["statusCode"] == 501
        r = funcion(evento("GET /publico/{tenant_id}/{local_id}/reservas/disponibilidad",
                           {"tenant_id": "demo", "local_id": "no_existe"}, sub=None))
        assert r["statusCode"] == 404

    def test_webhook_exige_firma_hmac(self, nube):
        funcion = cargar("pedidos-externos").lambda_handler
        datos = b'{"pedido": 1}'
        params = {"plataforma": "demo", "tenant_id": "demo", "local_id": L_ID}
        mala = funcion(evento("POST /webhooks/{plataforma}/{tenant_id}/{local_id}", params, datos, sub=None, command_id=None,
                              encabezados={"x-firma": "00"}))
        assert mala["statusCode"] == 401
        firma = hmac.new(b"secreto-de-prueba", datos, hashlib.sha256).hexdigest()
        buena = funcion(evento("POST /webhooks/{plataforma}/{tenant_id}/{local_id}", params, datos, sub=None,
                               command_id=None, encabezados={"x-firma": firma}))
        assert buena["statusCode"] == 501
