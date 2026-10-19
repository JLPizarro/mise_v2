"""Valida un despliegue de punta a punta: inicio de sesión, comanda, impresión, cobro, cierre y reporte.

Solo biblioteca estándar en el modo real. Dos modos:

  Real (contra AWS):
      set POS_ID_TOKEN=<ID token de Google de un dueño o admin>      (PowerShell: $env:POS_ID_TOKEN="...")
      python scripts/validar_despliegue.py --api https://<id>.execute-api.us-east-1.amazonaws.com/prod --local local_01
    Opcional, para validar también la impresión desde la nube (simula la impresora de cocina):
      set POS_CLAVE_IMPRESORA=mock-clave-cocina
      ... --tenant demo --impresora imp_cocina

  Simulado (sin AWS ni Google, con los datos mock de la semilla; requiere requirements-dev.txt):
      python scripts/validar_despliegue.py --simulado

Qué recorre:
   0. Token: emisor, audiencia y vigencia (el emisor debe coincidir con el del autorizador JWT).
   1. GET /salud y GET /yo (la cuenta debe ser dueño o admin del local).
   2. Plano y carta; abre una mesa libre con un pedido_id propuesto por el cliente.
   3. Agrega un ítem y repite el MISMO X-Command-Id: debe responder igual y escribir una sola vez.
   4. Envía la tanda; si hay clave de impresora, hace el ciclo CloudPRNT (consulta, descarga, confirma).
   5. Abre turno si no hay; precuenta, pago en efectivo con propina, finalizar con boleta.
   6. Espera el documento tributario `emitido` (Streams -> procesador -> SQS -> emision-dte).
   7. Si el turno lo abrió esta validación: conteo exacto, conciliación y cierre sin diferencia.
   8. Espera el reporte del turno con la venta en los agregados.
Termina con código 0 si todo pasó y 1 si algo falló.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def pesos(monto: int) -> str:
    return "$" + f"{monto:,}".replace(",", ".")


def ulid() -> str:
    def codificar(valor: int, largo: int) -> str:
        return "".join(_ALFABETO[(valor >> (5 * i)) & 31] for i in reversed(range(largo)))
    return codificar(time.time_ns() // 1_000_000, 10) + codificar(secrets.randbits(80), 16)


@dataclass
class Respuesta:
    http: int
    cuerpo: object
    encabezados: dict = field(default_factory=dict)


# --- transportes ---------------------------------------------------------------------------------------

class TransporteHttp:
    def __init__(self, api: str, token: str, espera_maxima: int):
        self.api = api.rstrip("/")
        self.token = token
        self.espera_maxima = espera_maxima

    def llamar(self, metodo: str, ruta: str, cuerpo=None, *, command_id: str | None = None,
               encabezados: dict | None = None, autenticar: bool = True, query: dict | None = None) -> Respuesta:
        url = self.api + ruta
        if query:
            url += "?" + "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in query.items())
        cabeceras = {"content-type": "application/json", **(encabezados or {})}
        if autenticar:
            cabeceras["authorization"] = f"Bearer {self.token}"
        if command_id:
            cabeceras["x-command-id"] = command_id
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        peticion = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras)
        try:
            with urllib.request.urlopen(peticion, timeout=15) as r:
                return Respuesta(r.status, _leer(r.read(), r.headers.get("content-type", "")),
                                 {k.lower(): v for k, v in r.headers.items()})
        except urllib.error.HTTPError as error:
            return Respuesta(error.code, _leer(error.read(), error.headers.get("content-type", "")),
                             {k.lower(): v for k, v in error.headers.items()})

    def esperar(self) -> None:
        time.sleep(3)


def _leer(datos: bytes, tipo: str):
    texto = datos.decode("utf-8", "replace")
    if "json" in tipo:
        try:
            return json.loads(texto)
        except ValueError:
            return texto
    return texto


class TransporteSimulado:
    """Toda la nube en memoria (moto): tablas, colas, temas y bucket, con la semilla mock. Las
    funciones se invocan con eventos del API Gateway (formato 2.0) y los procesos asíncronos se
    bombean a mano: Streams -> procesador-eventos y SQS -> emision-dte."""

    FUNCIONES_HTTP = ("salon", "pedidos", "caja", "administracion", "reportes", "impresion", "contingencia",
                      "reservas", "pedidos-externos", "mensajeria")

    def __init__(self, sub: str = "mock-dueno"):
        sys.path.insert(0, str(RAIZ / "lambdas" / "capa" / "python"))
        import importlib.util

        import boto3
        from moto import mock_aws

        for nombre, valor in {"AWS_DEFAULT_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": "simulado",
                              "AWS_SECRET_ACCESS_KEY": "simulado"}.items():
            os.environ.setdefault(nombre, valor)
        self._mock = mock_aws()
        self._mock.start()
        self.sub = sub
        self.espera_maxima = 5
        self.dynamo = boto3.client("dynamodb", region_name="us-east-1")
        for tabla in ("operacion", "configuracion"):
            self.dynamo.create_table(
                TableName=tabla, BillingMode="PAY_PER_REQUEST",
                AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "GSI1PK", "GSI1SK")],
                KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
                GlobalSecondaryIndexes=[{"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"}, "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]}])
        self.sqs = boto3.client("sqs", region_name="us-east-1")
        self.cola_dte = self.sqs.create_queue(QueueName="dte-emision")["QueueUrl"]
        cola_contingencia = self.sqs.create_queue(QueueName="contingencia-comandas.fifo",
                                                  Attributes={"FifoQueue": "true"})["QueueUrl"]
        self.sqs.create_queue(QueueName="dte-emision-fallidos")
        self.sqs.create_queue(QueueName="contingencia-comandas-fallidos.fifo", Attributes={"FifoQueue": "true"})
        sns = boto3.client("sns", region_name="us-east-1")
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="pos-archivo-simulado")
        os.environ.update({
            "TABLA_OPERACION": "operacion", "TABLA_CONFIGURACION": "configuracion", "COLA_DTE_URL": self.cola_dte,
            "COLA_CONTINGENCIA_URL": cola_contingencia, "BUCKET_ARCHIVO": "pos-archivo-simulado",
            "TEMA_DUENO_ARN": sns.create_topic(Name="pos-avisos-dueno")["TopicArn"],
            "TEMA_ALERTAS_ARN": sns.create_topic(Name="pos-alertas-tecnicas")["TopicArn"],
            "SECRETO_WEBHOOK": "simulado", "DTE_MODO": "ok", "LOG_LEVEL": "ERROR", "ESPERA_SQS_SEGUNDOS": "0",
        })

        from pos_dominio.infra import aws, identidad
        aws.reiniciar()
        identidad.limpiar_cache()

        def cargar(carpeta: Path):
            nombre = f"simulado_{carpeta.parent.name}_{carpeta.name.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(nombre, carpeta / "lambda_function.py")
            modulo = importlib.util.module_from_spec(spec)
            sys.modules[nombre] = modulo
            spec.loader.exec_module(modulo)
            return modulo

        semilla = cargar(RAIZ / "lambdas" / "herramientas" / "semilla")
        semilla.sembrar(self.dynamo, {"configuracion": "configuracion", "operacion": "operacion"})
        funciones = RAIZ / "lambdas" / "funciones"
        self.rutas = []
        for nombre in self.FUNCIONES_HTTP:
            app = cargar(funciones / nombre).lambda_handler
            for route_key in app.rutas:
                metodo, plantilla = route_key.split(" ", 1)
                patron = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", plantilla) + "$")
                self.rutas.append((metodo, patron, route_key, app))
        self.procesador = cargar(funciones / "procesador-eventos")
        self.emision = cargar(funciones / "emision-dte")
        self._vistos: set[str] = set()

    def cerrar(self) -> None:
        self._mock.stop()

    def llamar(self, metodo: str, ruta: str, cuerpo=None, *, command_id: str | None = None,
               encabezados: dict | None = None, autenticar: bool = True, query: dict | None = None) -> Respuesta:
        for metodo_ruta, patron, route_key, app in self.rutas:
            coincidencia = patron.match(ruta)
            if metodo_ruta == metodo and coincidencia:
                break
        else:
            return Respuesta(404, {"codigo": "RUTA_NO_ENCONTRADA"})
        cabeceras = {"content-type": "application/json", **(encabezados or {})}
        if command_id:
            cabeceras["x-command-id"] = command_id
        contexto = {"requestId": f"sim-{ulid()}", "routeKey": route_key, "http": {"method": metodo, "path": ruta}}
        if autenticar:
            contexto["authorizer"] = {"jwt": {"claims": {"sub": self.sub, "email": f"{self.sub}@demo.invalid",
                                                         "email_verified": "true", "name": self.sub}}}
        evento = {"version": "2.0", "routeKey": route_key, "headers": cabeceras, "requestContext": contexto,
                  "pathParameters": coincidencia.groupdict(), "queryStringParameters": query,
                  "body": json.dumps(cuerpo) if cuerpo is not None else None, "isBase64Encoded": False}
        r = app(evento)
        encabezados_respuesta = {k.lower(): v for k, v in r.get("headers", {}).items()}
        respuesta = Respuesta(r["statusCode"], _leer((r.get("body") or "").encode(), encabezados_respuesta.get("content-type", "")),
                              encabezados_respuesta)
        self.esperar()
        return respuesta

    def esperar(self) -> None:
        """Bombea los procesos asíncronos hasta que no quede nada pendiente."""
        for _ in range(6):
            nuevos = []
            for tabla_item in self.dynamo.scan(TableName="operacion")["Items"]:
                sk = tabla_item["SK"]["S"]
                if sk.startswith("EVT#") and sk not in self._vistos:
                    self._vistos.add(sk)
                    nuevos.append(tabla_item)
            if nuevos:
                registros = [{"eventName": "INSERT", "dynamodb": {"NewImage": i, "SequenceNumber": i["SK"]["S"],
                                                                  "Keys": {"PK": i["PK"], "SK": i["SK"]}}}
                             for i in sorted(nuevos, key=lambda i: i["SK"]["S"])]
                self.procesador.lambda_handler({"Records": registros})
            mensajes = self.sqs.receive_message(QueueUrl=self.cola_dte, MaxNumberOfMessages=10,
                                                AttributeNames=["All"]).get("Messages", [])
            if mensajes:
                registros = [{"messageId": m["MessageId"], "receiptHandle": m["ReceiptHandle"], "body": m["Body"],
                              "attributes": m.get("Attributes", {})} for m in mensajes]
                fallidos = {f["itemIdentifier"] for f in self.emision.lambda_handler({"Records": registros})["batchItemFailures"]}
                for m in mensajes:
                    if m["MessageId"] not in fallidos:
                        self.sqs.delete_message(QueueUrl=self.cola_dte, ReceiptHandle=m["ReceiptHandle"])
            if not nuevos and not mensajes:
                return


# --- validación -------------------------------------------------------------------------------------------

class Fallo(Exception):
    pass


class Validacion:
    def __init__(self, t, args):
        self.t, self.args = t, args
        self.L = f"/locales/{args.local}"
        self.resultados: list[tuple[str, bool, str]] = []

    def paso(self, nombre: str, funcion) -> object:
        inicio = time.monotonic()
        try:
            detalle = funcion()
            self.resultados.append((nombre, True, detalle or ""))
            print(f"  ✔ {nombre}  ({int((time.monotonic() - inicio) * 1000)} ms) {detalle or ''}")
            return detalle
        except Fallo as error:
            self.resultados.append((nombre, False, str(error)))
            print(f"  ✘ {nombre}: {error}")
            raise

    def exigir(self, r: Respuesta, *esperados: int, que: str = "") -> object:
        if r.http not in esperados:
            raise Fallo(f"{que or 'respuesta'}: HTTP {r.http} (esperado {esperados}) {json.dumps(r.cuerpo, ensure_ascii=False)[:300]}")
        return r.cuerpo

    def escribir(self, metodo: str, ruta: str, cuerpo=None, *esperados: int, command_id: str | None = None):
        r = self.t.llamar(metodo, self.L + ruta, cuerpo, command_id=command_id or ulid())
        return self.exigir(r, *(esperados or (200, 201)), que=f"{metodo} {ruta}")

    def leer(self, ruta: str, *esperados: int, query: dict | None = None):
        return self.exigir(self.t.llamar("GET", self.L + ruta, query=query), *(esperados or (200,)), que=f"GET {ruta}")

    def esperar(self, descripcion: str, condicion) -> object:
        limite = time.monotonic() + self.t.espera_maxima * 30
        while True:
            valor = condicion()
            if valor:
                return valor
            if time.monotonic() > limite:
                raise Fallo(f"tiempo agotado esperando {descripcion}")
            self.t.esperar()

    def ejecutar(self) -> bool:
        a = self.args
        estado: dict = {}
        try:
            if isinstance(self.t, TransporteHttp):
                self.paso("token de Google", self.revisar_token)
            self.paso("GET /salud", lambda: self.exigir(self.t.llamar("GET", "/salud", autenticar=False), 200) and "DynamoDB ok")

            def yo():
                cuerpo = self.exigir(self.t.llamar("GET", "/yo"), 200, que="GET /yo")
                local = next((x for x in cuerpo["locales"] if x["local_id"] == a.local), None)
                if local is None:
                    raise Fallo(f"la cuenta {cuerpo.get('email')} no tiene acceso al local {a.local}")
                if local["rol"] not in ("dueno", "admin"):
                    raise Fallo(f"rol {local['rol']}: usa una cuenta de dueño o admin")
                estado["tenant"] = local["tenant_id"]
                return f"{cuerpo.get('email')} es {local['rol']} en {local['nombre_local']}"
            self.paso("GET /yo", yo)

            def plano_y_carta():
                mesas = self.leer("/salon")["mesas"]
                libre = next((m for m in mesas if m["estado"] == "libre"), None)
                if libre is None:
                    raise Fallo("no hay mesas libres")
                productos = [p for p in self.leer("/catalogo")["productos"] if p["activo"]]
                producto = next((p for p in productos if p["producto_id"] == a.producto), productos[0] if productos else None)
                if producto is None:
                    raise Fallo("la carta no tiene productos activos")
                estado.update(mesa=libre["mesa_id"], producto=producto)
                return f"mesa {libre.get('numero', libre['mesa_id'])}, producto {producto['nombre']}"
            self.paso("plano y carta", plano_y_carta)

            def abrir():
                propuesto = ulid()
                pedido = self.escribir("POST", "/pedidos", {"mesa_id": estado["mesa"], "pedido_id": propuesto}, 201)
                if pedido["pedido_id"] != propuesto:
                    raise Fallo("el servidor no respetó el pedido_id propuesto")
                estado["pedido"] = propuesto
                return propuesto
            self.paso("abrir mesa", abrir)

            def agregar_idempotente():
                comando = ulid()
                ruta = f"{self.L}/pedidos/{estado['pedido']}/items"
                cuerpo = {"producto_id": estado["producto"]["producto_id"], "cantidad": 2, "mesa_id": estado["mesa"]}
                primera = self.t.llamar("POST", ruta, cuerpo, command_id=comando)
                segunda = self.t.llamar("POST", ruta, cuerpo, command_id=comando)
                self.exigir(primera, 201, que="agregar ítem")
                if segunda.cuerpo != primera.cuerpo or segunda.encabezados.get("x-comando-repetido") != "true":
                    raise Fallo("el mismo X-Command-Id no devolvió la respuesta guardada")
                pedido = self.leer(f"/pedidos/{estado['pedido']}")
                if len(pedido["items"]) != 1 or pedido["total"] != estado["producto"]["precio"] * 2:
                    raise Fallo(f"se escribió más de una vez: {len(pedido['items'])} ítems, total {pedido['total']}")
                estado["total"] = pedido["total"]
                return "una sola escritura"
            self.paso("idempotencia (mismo X-Command-Id dos veces)", agregar_idempotente)

            def enviar():
                tanda = self.escribir("POST", f"/pedidos/{estado['pedido']}/enviar", {"mesa_id": estado["mesa"]}, 200)
                return ", ".join(f"{x['cuarto']}: {x['estado']}" for x in tanda["impresion"])
            self.paso("enviar tanda a cocina", enviar)

            if a.clave_impresora:
                self.paso("impresión CloudPRNT", lambda: self.imprimir(estado))
            else:
                print("  - impresión CloudPRNT: omitida (define POS_CLAVE_IMPRESORA para validarla)")

            def turno():
                r = self.t.llamar("GET", self.L + "/caja/turno")
                if r.http == 404:
                    abierto = self.escribir("POST", "/caja/turnos", {"monto_apertura": 0}, 201)
                    estado.update(turno=abierto["turno_id"], abrimos_turno=True, apertura=0)
                    return "turno abierto por la validación"
                cuerpo = self.exigir(r, 200, que="turno actual")
                estado.update(turno=cuerpo["turno_id"], abrimos_turno=False, apertura=cuerpo["monto_apertura"])
                return "se usa el turno ya abierto (no se cerrará)"
            self.paso("turno de caja", turno)

            def cobrar():
                self.escribir("POST", f"/pedidos/{estado['pedido']}/precuenta", {"mesa_id": estado["mesa"]}, 200)
                propina = (estado["total"] * 10 + 50) // 100
                pago = self.escribir("POST", f"/pedidos/{estado['pedido']}/pagos", {"medios": [
                    {"metodo": "efectivo", "monto": estado["total"], "propina": propina,
                     "efectivo_recibido": estado["total"] + propina}]}, 201)
                if pago["pedido"]["saldo"] != 0:
                    raise Fallo("quedó saldo pendiente")
                estado["efectivo"] = estado["total"] + propina
                final = self.escribir("POST", f"/pedidos/{estado['pedido']}/finalizar", {"tipo_documento": "boleta"}, 200)
                return f"total {pesos(estado['total'])} + propina {pesos(propina)}, documento {final['documento']['estado']}"
            self.paso("precuenta, cobro y cierre de la venta", cobrar)

            def documento():
                doc = self.esperar("el documento tributario", lambda: (
                    d := self.leer(f"/caja/documentos/{estado['pedido']}"))["estado"] not in ("pendiente", "enviando") and d)
                if doc["estado"] != "emitido":
                    raise Fallo(f"documento {doc['estado']}: {doc.get('motivo_rechazo')}")
                return f"folio {doc['folio']}"
            self.paso("documento tributario emitido (asíncrono)", documento)

            if estado["abrimos_turno"]:
                def cerrar():
                    conteo = self.escribir("POST", f"/caja/turnos/{estado['turno']}/conteo",
                                           {"monto": estado["apertura"] + estado["efectivo"]}, 200)
                    if conteo["requiere_segundo_conteo"]:
                        raise Fallo("el conteo exacto pidió recuento")
                    self.escribir("POST", f"/caja/turnos/{estado['turno']}/conciliacion",
                                  {"total_debito_pos": 0, "total_credito_pos": 0}, 200)
                    cierre = self.escribir("POST", f"/caja/turnos/{estado['turno']}/cerrar", {}, 200)
                    if cierre["diferencia_efectivo"] != 0:
                        raise Fallo(f"diferencia {cierre['diferencia_efectivo']}")
                    return "arqueo ciego sin diferencia"
                self.paso("cierre de turno", cerrar)

            def reporte():
                datos = self.esperar("los agregados del turno", lambda: (
                    r := self.leer(f"/reportes/turnos/{estado['turno']}"))["resumen"].get("n_ventas") and r)
                return f"{datos['resumen']['n_ventas']} venta(s), {pesos(datos['resumen']['total_ventas'])}"
            self.paso("reporte del turno (agregados asíncronos)", reporte)

            def mensajeria():
                # Destino temporal de tipo cola con una regla; el aviso de prueba debe llegar a él y a nadie más.
                destino = self.escribir("POST", "/mensajeria/destinos", {
                    "nombre": f"Validación {ulid()[-6:]}", "tipo": "cola", "avisos": ["documento_rechazado"]}, 201)
                try:
                    prueba = self.escribir("POST", "/mensajeria/pruebas", {"aviso": "documento_rechazado"}, 200)
                    if destino["destino_id"] not in [d["destino_id"] for d in prueba["destinos_esperados"]]:
                        raise Fallo("la regla no incluye al destino recién creado")
                    self.esperar("el aviso en la cola del destino", lambda: self.leer(
                        f"/mensajeria/destinos/{destino['destino_id']}/mensajes")["mensajes"])
                finally:
                    self.escribir("DELETE", f"/mensajeria/destinos/{destino['destino_id']}", None, 200)
                return "destino creado, aviso de prueba recibido por la regla y destino eliminado"
            self.paso("mensajería: destino, regla y aviso de prueba", mensajeria)
        except Fallo:
            pass
        bien = all(ok for _, ok, _ in self.resultados)
        print(f"\n{'VALIDACIÓN COMPLETA' if bien else 'VALIDACIÓN CON FALLAS'}: "
              f"{sum(ok for _, ok, _ in self.resultados)}/{len(self.resultados)} pasos")
        return bien

    def revisar_token(self) -> str:
        try:
            carga = self.t.token.split(".")[1]
            datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
        except (IndexError, ValueError) as error:
            raise Fallo("POS_ID_TOKEN no es un JWT (¿pegaste el token de acceso en vez del ID token?)") from error
        if datos.get("iss") != self.args.emisor:
            raise Fallo(f"el emisor del token es '{datos.get('iss')}' y el autorizador espera '{self.args.emisor}'. "
                        f"Cambia el emisor del autorizador JWT a '{datos.get('iss')}' y vuelve a desplegar el stage.")
        restante = int(datos.get("exp", 0) - time.time())
        if restante < 120:
            raise Fallo("el token vence en menos de 2 minutos; obtén uno nuevo")
        if str(datos.get("email_verified")).lower() != "true":
            raise Fallo("el email de la cuenta no está verificado")
        return f"iss={datos['iss']} aud={datos.get('aud')} vence en {restante // 60} min"

    def imprimir(self, estado) -> str:
        a = self.args
        ruta = f"/impresion/{estado['tenant']}/{a.local}/{a.impresora}"
        basic = {"authorization": "Basic " + base64.b64encode(f"{a.impresora}:{a.clave_impresora}".encode()).decode()}
        consulta = self.exigir(self.t.llamar("POST", ruta, {"status": "200 OK"}, autenticar=False, encabezados=basic),
                               200, que="consulta de la impresora")
        if not consulta.get("jobReady"):
            raise Fallo(f"la impresora {a.impresora} no tiene trabajos (¿el producto se imprime en otro cuarto?)")
        token = consulta["jobToken"]
        texto = self.exigir(self.t.llamar("GET", ruta, autenticar=False, encabezados=basic,
                                          query={"token": token, "type": "text/plain"}), 200, que="descarga del trabajo")
        if "x" not in str(texto):
            raise Fallo("el trabajo descargado no parece una comanda")
        self.exigir(self.t.llamar("DELETE", ruta, autenticar=False, encabezados=basic,
                                  query={"token": token, "code": "200 OK"}), 200, que="confirmación")
        return f"trabajo {token} impreso y confirmado"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Valida un despliegue del POS de punta a punta.")
    parser.add_argument("--api", help="URL del stage, p. ej. https://abc123.execute-api.us-east-1.amazonaws.com/prod")
    parser.add_argument("--simulado", action="store_true", help="todo en memoria con moto y datos mock")
    parser.add_argument("--local", default="local_01")
    parser.add_argument("--tenant", default="demo")
    parser.add_argument("--producto", default="pizza")
    parser.add_argument("--impresora", default="imp_cocina")
    parser.add_argument("--emisor", default=os.environ.get("POS_EMISOR", "https://accounts.google.com"))
    args = parser.parse_args(argv)
    args.clave_impresora = os.environ.get("POS_CLAVE_IMPRESORA")

    if args.simulado:
        print("Validación SIMULADA (moto + datos mock, sin AWS ni Google)")
        transporte = TransporteSimulado()
        args.clave_impresora = args.clave_impresora or "mock-clave-cocina"
        try:
            return 0 if Validacion(transporte, args).ejecutar() else 1
        finally:
            transporte.cerrar()
    token = os.environ.get("POS_ID_TOKEN", "").strip()
    if not args.api or not token:
        parser.error("en modo real se necesitan --api y la variable de entorno POS_ID_TOKEN")
    print(f"Validación contra {args.api}")
    return 0 if Validacion(TransporteHttp(args.api, token, espera_maxima=4), args).ejecutar() else 1


if __name__ == "__main__":
    sys.exit(main())
