"""Servidor local de desarrollo: emula el API Gateway con las Lambdas reales y datos simulados en memoria.

Con él la PWA se desarrolla y se prueba completa sin AWS y sin el ID de cliente de Google:

    python scripts/servidor_local.py [--puerto 8001] [--origen http://localhost:8000]

Requiere requirements-dev.txt (moto). Reutiliza `TransporteSimulado` de validar_despliegue.py: tablas,
colas, semilla mock y funciones cargadas. Solo atiende en esta máquina (127.0.0.1).

Ingreso de desarrollo: `Authorization: Bearer dev:<sub>` (por ejemplo `dev:mock-cajero`). El API
Gateway real rechaza ese token, así que esto no abre nada en la nube.

Fallas para probar la contingencia:
    curl -X POST http://localhost:8001/__dev/fallas -d "{\\"rutas_normales\\": true}"
    curl -X POST http://localhost:8001/__dev/fallas -d "{\\"dynamodb\\": true}"
    curl http://localhost:8001/__dev/fallas
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import rutas_api  # noqa: E402
from validar_despliegue import TransporteSimulado, ulid  # noqa: E402

PERSONAS = (
    ("mock-dueno", "código de autorización 1234"), ("mock-admin", "código de autorización 4321"),
    ("mock-cajero", ""), ("mock-garzon", ""), ("mock-garzon2", ""), ("mock-cocina", ""),
)
SIEMPRE_DISPONIBLES = ("GET /yo", "POST /contingencia/comandas")
FALLAS_INICIALES = {"rutas_normales": False, "dynamodb": False}


class TransporteLocal(TransporteSimulado):
    """TransporteSimulado más el bombeo de contingencia-comandas.fifo -> drenador-contingencia."""

    def __init__(self) -> None:
        super().__init__()
        ruta = RAIZ / "lambdas" / "funciones" / "drenador-contingencia" / "lambda_function.py"
        spec = importlib.util.spec_from_file_location("simulado_funciones_drenador_contingencia", ruta)
        self.drenador = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.drenador
        spec.loader.exec_module(self.drenador)
        self.cola_contingencia = os.environ["COLA_CONTINGENCIA_URL"]

    def esperar(self) -> None:
        super().esperar()
        self.bombear_contingencia()

    def bombear_contingencia(self) -> None:
        """Recibe hasta 10, invoca, borra los que no fallaron. Los que fallan quedan para el próximo intento."""
        for _ in range(6):
            mensajes = self.sqs.receive_message(QueueUrl=self.cola_contingencia, MaxNumberOfMessages=10,
                                                AttributeNames=["All"]).get("Messages", [])
            if not mensajes:
                return
            registros = [{"messageId": m["MessageId"], "receiptHandle": m["ReceiptHandle"], "body": m["Body"],
                          "attributes": m.get("Attributes", {})} for m in mensajes]
            respuesta = self.drenador.lambda_handler({"Records": registros})
            fallidos = {f["itemIdentifier"] for f in respuesta["batchItemFailures"]}
            for m in mensajes:
                if m["MessageId"] in fallidos:
                    self.sqs.change_message_visibility(QueueUrl=self.cola_contingencia, ReceiptHandle=m["ReceiptHandle"],
                                                       VisibilityTimeout=0)
                else:
                    self.sqs.delete_message(QueueUrl=self.cola_contingencia, ReceiptHandle=m["ReceiptHandle"])
            if fallidos:
                return
        # Más de 60 mensajes: el resto se drena en la próxima petición.


class ServidorLocal(HTTPServer):
    transporte: TransporteLocal
    origen: str
    fallas: dict
    privadas: dict

    def cerrar_todo(self) -> None:
        """Libera el puerto y detiene la nube simulada."""
        self.server_close()
        self.transporte.cerrar()
        os.environ.pop("SIMULAR_FALLA_DYNAMODB", None)


class Manejador(BaseHTTPRequestHandler):
    server: ServidorLocal

    def log_message(self, formato, *args) -> None:  # noqa: A002
        print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    # --- verbos ---
    def do_OPTIONS(self) -> None:
        self._responder(204, {}, b"", con_tipo=False)
        return

    def do_GET(self) -> None:
        self._atender()

    def do_POST(self) -> None:
        self._atender()

    def do_PATCH(self) -> None:
        self._atender()

    def do_DELETE(self) -> None:
        self._atender()

    # --- implementación ---
    def _responder(self, estado: int, encabezados: dict, cuerpo: bytes, con_tipo: bool = True) -> None:
        self.send_response(estado)
        for nombre, valor in encabezados.items():
            if nombre.lower() not in ("content-length", "access-control-allow-origin"):
                self.send_header(nombre, str(valor))
        self.send_header("Access-Control-Allow-Origin", self.server.origen)
        self.send_header("Access-Control-Expose-Headers", "x-comando-repetido")
        if self.command == "OPTIONS":
            self.send_header("Access-Control-Allow-Headers", "authorization,content-type,x-command-id")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE")
            self.send_header("Access-Control-Max-Age", "600")
        if con_tipo and not any(n.lower() == "content-type" for n in encabezados):
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        if cuerpo:
            self.wfile.write(cuerpo)

    def _json(self, estado: int, datos: object) -> None:
        self._responder(estado, {}, json.dumps(datos).encode())

    def _atender(self) -> None:
        partes = urlsplit(self.path)
        ruta = partes.path
        largo = int(self.headers.get("Content-Length") or 0)
        texto = self.rfile.read(largo).decode("utf-8", "replace") if largo else None

        if ruta == "/__dev/fallas":
            return self._fallas(texto)

        transporte = self.server.transporte
        for metodo, patron, route_key, app in transporte.rutas:
            coincidencia = patron.match(ruta)
            if metodo == self.command and coincidencia:
                break
        else:
            return self._json(404, {"message": "Not Found"})

        encabezados = {k.lower(): v for k, v in self.headers.items()}
        contexto = {"requestId": f"local-{ulid()}", "routeKey": route_key,
                    "http": {"method": self.command, "path": ruta}}
        if self.server.privadas.get(route_key):
            autorizacion = encabezados.get("authorization", "")
            if not re.fullmatch(r"Bearer dev:[\w.-]+", autorizacion):
                return self._json(401, {"message": "Unauthorized"})
            sub = autorizacion.removeprefix("Bearer dev:")
            contexto["authorizer"] = {"jwt": {"claims": {"sub": sub, "email": f"{sub}@demo.invalid",
                                                         "email_verified": "true", "name": sub}}}
            if self.server.fallas["rutas_normales"] and route_key not in SIEMPRE_DISPONIBLES:
                return self._json(503, {"message": "Service Unavailable"})

        consulta = {k: v[-1] for k, v in parse_qs(partes.query, keep_blank_values=True).items()} or None
        evento = {"version": "2.0", "routeKey": route_key, "headers": encabezados, "requestContext": contexto,
                  "pathParameters": coincidencia.groupdict(), "queryStringParameters": consulta,
                  "body": texto, "isBase64Encoded": False}
        resultado = app(evento)
        transporte.esperar()
        cuerpo = resultado.get("body") or ""
        self._responder(resultado["statusCode"], resultado.get("headers", {}), cuerpo.encode())

    def _fallas(self, texto: str | None) -> None:
        if self.command == "POST":
            try:
                datos = json.loads(texto or "{}")
            except ValueError:
                return self._json(400, {"message": "JSON inválido"})
            for clave in FALLAS_INICIALES:
                if clave in datos:
                    self.server.fallas[clave] = bool(datos[clave])
            if self.server.fallas["dynamodb"]:
                os.environ["SIMULAR_FALLA_DYNAMODB"] = "true"
            else:
                os.environ.pop("SIMULAR_FALLA_DYNAMODB", None)
        elif self.command != "GET":
            return self._json(404, {"message": "Not Found"})
        self._json(200, self.server.fallas)


def crear_servidor(puerto: int, origen: str) -> ServidorLocal:
    """Levanta la nube simulada y el servidor (de un solo hilo: moto no es seguro entre hilos)."""
    transporte = TransporteLocal()
    servidor = ServidorLocal(("127.0.0.1", puerto), Manejador)
    servidor.transporte = transporte
    servidor.origen = origen
    servidor.fallas = dict(FALLAS_INICIALES)
    servidor.privadas = {f"{m} {r}": jwt for m, r, _, jwt in rutas_api.rutas()}
    return servidor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Servidor local que emula el API Gateway del POS.")
    parser.add_argument("--puerto", type=int, default=8001)
    parser.add_argument("--origen", default="http://localhost:8000", help="origen permitido por CORS (la PWA)")
    args = parser.parse_args(argv)

    print("Levantando la nube simulada (moto + datos mock)…")
    servidor = crear_servidor(args.puerto, args.origen)
    print(f"API simulada:     http://localhost:{args.puerto}")
    print(f"Origen permitido: {args.origen}")
    print("Personas mock (ingreso de desarrollo, Authorization: Bearer dev:<sub>):")
    for sub, nota in PERSONAS:
        print(f"  {sub}" + (f"  ({nota})" if nota else ""))
    print("Simulador de impresora de cocina (otra terminal):")
    print(f"  POS_CLAVE_IMPRESORA=mock-clave-cocina python scripts/simulador_impresora.py "
          f"--api http://localhost:{args.puerto} --impresora imp_cocina")
    print("Fallas: POST /__dev/fallas {\"rutas_normales\": true} o {\"dynamodb\": true}\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo…")
    finally:
        servidor.cerrar_todo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
