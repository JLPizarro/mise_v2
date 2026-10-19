"""API Gateway HTTP API, formato de carga 2.0: lectura del evento, respuestas y despacho por routeKey.

- El cuerpo puede venir en base64 (isBase64Encoded); se decodifica antes de leerlo.
- Los números con decimales del JSON se leen como Decimal (nunca float): un monto con decimales
  falla la validación de entero en vez de redondearse en silencio.
- Errores siempre como {"codigo", "mensaje", "requestId"} (más "detalle" cuando aporta).
- Las escrituras exigen el encabezado X-Command-Id (ULID).
- Las funciones de la API tienen 10 s de tiempo máximo; el API Gateway corta a los 30 s.
"""

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal

from pos_dominio import validacion
from pos_dominio.errores import ErrorDeCodigo, ErrorDominio, ErrorInfraestructura
from pos_dominio.infra import logs
from pos_dominio.infra.dynamodb import normalizar

log = logging.getLogger("pos.http")


class PeticionInvalida(ErrorDominio):
    http = 400
    codigo = "PETICION_INVALIDA"


class RutaNoEncontrada(ErrorDominio):
    http = 404
    codigo = "RUTA_NO_ENCONTRADA"


@dataclass
class Peticion:
    evento: dict
    route_key: str
    metodo: str
    parametros: dict
    query: dict
    encabezados: dict
    cuerpo_bytes: bytes
    request_id: str
    command_id: str = ""
    _json: dict | None = field(default=None, repr=False)

    @property
    def claims(self) -> dict:
        return (self.evento.get("requestContext", {}).get("authorizer", {}).get("jwt", {}) or {}).get("claims") or {}

    @property
    def ip(self) -> str:
        return self.evento.get("requestContext", {}).get("http", {}).get("sourceIp", "")

    def json(self) -> dict:
        if self._json is None:
            if not self.cuerpo_bytes.strip():
                self._json = {}
            else:
                try:
                    datos = json.loads(self.cuerpo_bytes.decode("utf-8"), parse_float=Decimal)
                except (UnicodeDecodeError, ValueError) as error:
                    raise PeticionInvalida("El cuerpo no es JSON válido", codigo="JSON_INVALIDO") from error
                if not isinstance(datos, dict):
                    raise PeticionInvalida("El cuerpo debe ser un objeto JSON", codigo="JSON_INVALIDO")
                self._json = datos
        return self._json

    def cuerpo_con_ruta(self, *excluir: str) -> dict:
        """Cuerpo JSON con los parámetros de la ruta encima: la ruta manda, el cuerpo no puede
        cambiar el pedido, ítem o turno sobre el que se actúa."""
        return {**self.json(), **{k: v for k, v in self.parametros.items() if k not in excluir}}


def leer_evento(evento: dict) -> Peticion:
    cuerpo = evento.get("body") or ""
    if evento.get("isBase64Encoded"):
        try:
            cuerpo_bytes = base64.b64decode(cuerpo)
        except ValueError as error:
            raise PeticionInvalida("Cuerpo base64 inválido", codigo="BASE64_INVALIDO") from error
    else:
        cuerpo_bytes = cuerpo.encode("utf-8") if isinstance(cuerpo, str) else bytes(cuerpo)
    contexto = evento.get("requestContext", {})
    http = contexto.get("http", {})
    return Peticion(
        evento=evento,
        route_key=evento.get("routeKey") or contexto.get("routeKey", ""),
        metodo=http.get("method", ""),
        parametros=evento.get("pathParameters") or {},
        query=evento.get("queryStringParameters") or {},
        encabezados={k.lower(): v for k, v in (evento.get("headers") or {}).items()},
        cuerpo_bytes=cuerpo_bytes,
        request_id=contexto.get("requestId", ""),
    )


def respuesta(http: int, cuerpo, *, encabezados: dict | None = None) -> dict:
    return {
        "statusCode": http,
        "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store",
                    **(encabezados or {})},
        "body": json.dumps(cuerpo, ensure_ascii=False, separators=(",", ":"), default=normalizar),
    }


def respuesta_texto(http: int, texto: str, tipo: str = "text/plain; charset=utf-8") -> dict:
    return {"statusCode": http, "headers": {"content-type": tipo, "cache-control": "no-store"}, "body": texto}


def respuesta_error(http: int, codigo: str, mensaje: str, request_id: str, detalle: dict | None = None) -> dict:
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "requestId": request_id}
    if detalle:
        cuerpo["detalle"] = detalle
    return respuesta(http, cuerpo)


@dataclass
class Ruta:
    funcion: object
    escritura: bool
    publica: bool


class Aplicacion:
    """Despachador de una función Lambda de la API. Cada ruta es un routeKey exacto ("POST /x/{id}")."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.rutas: dict[str, Ruta] = {}

    def ruta(self, route_key: str, *, escritura: bool = False, publica: bool = False):
        def registrar(funcion):
            self.rutas[route_key] = Ruta(funcion, escritura, publica)
            return funcion
        return registrar

    def __call__(self, evento: dict, _contexto_lambda=None) -> dict:
        logs.configurar()
        inicio = time.monotonic()
        request_id = ""
        try:
            peticion = leer_evento(evento)
            request_id = peticion.request_id
            logs.correlacion(requestId=request_id, funcion=self.nombre, ruta=peticion.route_key)
            ruta = self.rutas.get(peticion.route_key)
            if ruta is None:
                raise RutaNoEncontrada(f"Ruta no atendida por {self.nombre}: {peticion.route_key}")
            if ruta.escritura:
                peticion.command_id = validacion.command_id(peticion.encabezados.get("x-command-id"))
                logs.correlacion(command_id=peticion.command_id)
            resultado = ruta.funcion(peticion)
            if isinstance(resultado, dict) and "statusCode" in resultado:
                return resultado
            http, cuerpo = resultado
            return respuesta(http, cuerpo)
        except ErrorDominio as error:
            log.info("rechazo", extra={"error_codigo": error.codigo, "http": error.http})
            return respuesta_error(error.http, error.codigo, error.mensaje, request_id, error.detalle)
        except ErrorInfraestructura as error:
            log.error("falla de infraestructura", extra={"causa": error.causa, "detalle_error": str(error)})
            return respuesta_error(503, "SERVICIO_NO_DISPONIBLE",
                                   "El servicio no está disponible en este momento. Intenta de nuevo.", request_id)
        except ErrorDeCodigo:
            log.exception("defecto de código")
            return respuesta_error(500, "ERROR_INTERNO", "Error interno", request_id)
        except Exception:  # noqa: BLE001 - toda excepción inesperada se registra y responde 500
            log.exception("error inesperado")
            return respuesta_error(500, "ERROR_INTERNO", "Error interno", request_id)
        finally:
            log.debug("fin", extra={"latencia_ms": int((time.monotonic() - inicio) * 1000)})
            logs.limpiar_correlacion()
