"""Adaptador de DynamoDB con boto3 (ya incluido en el runtime de Lambda).

- Toda expresión usa ExpressionAttributeNames: nunca choca con palabras reservadas (`total`,
  `estado`, `version`... `total` costó un 500 silencioso en la nube v1).
- Escritura: una sola TransactWriteItems con CMD + cambios + EVT (patrón outbox).
- Lectura: Decimal se convierte a int; nada sale como Decimal hacia el JSON.
- Escritura: un float es un defecto de código (boto3 lo rechaza); se detecta antes de enviar.
- Una transacción cancelada se interpreta por sus CancellationReasons (docs/migracion/01 §8):
  condición del CMD = duplicado; otra condición = rechazo de negocio o relectura; limitación,
  error interno o red = infraestructura (activa la contingencia en `pedidos`); ValidationError =
  defecto de código.
"""

import json
import logging
import os
import random
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from pos_dominio import claves, ids, tiempo
from pos_dominio.cambios import Borrar, Crear, Guardar, Reemplazar, Sumar, Evento
from pos_dominio.errores import (
    ComandoDuplicado, Conflicto, ErrorDeCodigo, ErrorDominio, ErrorInfraestructura, Reintentar,
)
from pos_dominio.modelos import (
    Bloqueo, ConfigLocal, Cuarto, Impresora, Item, Membresia, MesaEstado, MesaEstructura, Pago, Pedido, Producto,
    Turno,
)

log = logging.getLogger("pos.dynamodb")

TTL_CMD = 48 * 3600
TTL_EVT = 7 * 24 * 3600
MAX_ITEMS_TRANSACCION = 100
REINTENTOS_CONFLICTO = 2

_SERIALIZADOR = TypeSerializer()
_DESERIALIZADOR = TypeDeserializer()

_CODIGOS_INFRA = {
    "ThrottlingException", "ProvisionedThroughputExceededException", "RequestLimitExceeded",
    "InternalServerError", "ServiceUnavailable", "TransactionInProgressException", "AccessDeniedException",
    "UnrecognizedClientException", "ExpiredTokenException", "ResourceNotFoundException",
}
_MOTIVOS_INFRA = {"ThrottlingError", "ProvisionedThroughputExceeded", "RequestLimitExceeded",
                  "InternalServerError", "ServiceUnavailable"}


# --- conversión ----------------------------------------------------------------------------------

def _sin_float(valor, ruta: str = "") -> None:
    if isinstance(valor, float):
        raise ErrorDeCodigo(f"float no permitido en DynamoDB ({ruta or 'valor'}); usa enteros")
    if isinstance(valor, dict):
        for clave, sub in valor.items():
            _sin_float(sub, f"{ruta}.{clave}" if ruta else str(clave))
    elif isinstance(valor, (list, tuple, set)):
        for indice, sub in enumerate(valor):
            _sin_float(sub, f"{ruta}[{indice}]")


def a_dynamo(valor) -> dict:
    _sin_float(valor)
    return _SERIALIZADOR.serialize(valor)


def a_item(atributos: dict) -> dict:
    _sin_float(atributos)
    return {clave: _SERIALIZADOR.serialize(valor) for clave, valor in atributos.items()}


def normalizar(valor):
    """Decimal -> int (los montos siempre son enteros); recorre listas y dicts."""
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    if isinstance(valor, dict):
        return {k: normalizar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [normalizar(v) for v in valor]
    if isinstance(valor, set):
        return sorted(normalizar(v) for v in valor)
    return valor


def desde_item(item: dict | None) -> dict | None:
    if item is None:
        return None
    return {clave: normalizar(_DESERIALIZADOR.deserialize(valor)) for clave, valor in item.items()}


# --- condiciones ---------------------------------------------------------------------------------

class _Expresion:
    def __init__(self):
        self.nombres: dict[str, str] = {}
        self.valores: dict[str, dict] = {}
        self._por_atributo: dict[str, str] = {}

    def nombre(self, atributo: str) -> str:
        if atributo not in self._por_atributo:
            marcador = f"#a{len(self._por_atributo)}"
            self._por_atributo[atributo] = marcador
            self.nombres[marcador] = atributo
        return self._por_atributo[atributo]

    def valor(self, valor) -> str:
        marcador = f":v{len(self.valores)}"
        self.valores[marcador] = a_dynamo(valor)
        return marcador

    def condicion(self, arbol) -> str | None:
        if arbol is None:
            return None
        operador = arbol[0]
        if operador in ("=", "<>"):
            return f"{self.nombre(arbol[1])} {operador} {self.valor(arbol[2])}"
        if operador == "in":
            return f"{self.nombre(arbol[1])} IN ({', '.join(self.valor(x) for x in arbol[2])})"
        if operador == "existe":
            return f"attribute_exists({self.nombre(arbol[1])})"
        if operador == "no_existe":
            return f"attribute_not_exists({self.nombre(arbol[1])})"
        if operador in ("y", "o"):
            partes = [p for p in (self.condicion(c) for c in arbol[1]) if p]
            if not partes:
                return None
            union = " AND " if operador == "y" else " OR "
            return union.join(f"({p})" for p in partes) if len(partes) > 1 else partes[0]
        raise ErrorDeCodigo(f"condición desconocida: {operador}")

    def aplicar_a(self, operacion: dict, condicion: str | None) -> dict:
        if condicion:
            operacion["ConditionExpression"] = condicion
        if self.nombres:
            operacion["ExpressionAttributeNames"] = self.nombres
        if self.valores:
            operacion["ExpressionAttributeValues"] = self.valores
        return operacion


# --- almacén ---------------------------------------------------------------------------------------

class AlmacenDynamo:
    def __init__(self, cliente=None, *, tabla_operacion: str | None = None, tabla_configuracion: str | None = None,
                 reloj=time.time, dormir=time.sleep):
        self.cliente = cliente or boto3.client(
            "dynamodb",
            config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 3, "mode": "standard"}),
        )
        self.tablas = {
            claves.TABLA_OPERACION: tabla_operacion or os.environ.get("TABLA_OPERACION", "operacion"),
            claves.TABLA_CONFIGURACION: tabla_configuracion or os.environ.get("TABLA_CONFIGURACION", "configuracion"),
        }
        self._reloj = reloj
        self._dormir = dormir

    # --- primitivas de lectura ---

    def _simular_falla(self) -> None:
        # Simulacro de docs/migracion/05: SIMULAR_FALLA_DYNAMODB=true en `pedidos` fuerza una falla
        # de infraestructura sin tocar AWS, para probar la contingencia.
        if os.environ.get("SIMULAR_FALLA_DYNAMODB", "").lower() == "true":
            raise ErrorInfraestructura("Falla de DynamoDB simulada (SIMULAR_FALLA_DYNAMODB)", causa="simulada")

    def _llamar(self, metodo: str, **parametros):
        self._simular_falla()
        try:
            return getattr(self.cliente, metodo)(**parametros)
        except ClientError as error:
            raise _clasificar_error_cliente(error) from error
        except BotoCoreError as error:
            raise ErrorInfraestructura(f"DynamoDB no respondió: {type(error).__name__}", causa="red") from error

    def obtener(self, tabla: str, pk: str, sk: str, *, consistente: bool = True) -> dict | None:
        respuesta = self._llamar("get_item", TableName=self.tablas[tabla], ConsistentRead=consistente,
                                 Key={"PK": {"S": pk}, "SK": {"S": sk}})
        return desde_item(respuesta.get("Item"))

    def consultar(self, tabla: str, pk: str, *, prefijo: str | None = None, consistente: bool = True,
                  limite: int | None = None, indice: str | None = None) -> list[dict]:
        expresion = _Expresion()
        clave_pk = "GSI1PK" if indice else "PK"
        clave_sk = "GSI1SK" if indice else "SK"
        condicion = f"{expresion.nombre(clave_pk)} = {expresion.valor(pk)}"
        if prefijo:
            condicion += f" AND begins_with({expresion.nombre(clave_sk)}, {expresion.valor(prefijo)})"
        parametros = {"TableName": self.tablas[tabla], "KeyConditionExpression": condicion,
                      "ExpressionAttributeNames": expresion.nombres, "ExpressionAttributeValues": expresion.valores}
        if indice:
            parametros["IndexName"] = indice
        else:
            parametros["ConsistentRead"] = consistente
        if limite:
            parametros["Limit"] = limite
        items: list[dict] = []
        while True:
            respuesta = self._llamar("query", **parametros)
            items.extend(desde_item(i) for i in respuesta.get("Items", []))
            siguiente = respuesta.get("LastEvaluatedKey")
            if not siguiente or (limite and len(items) >= limite):
                return items
            parametros["ExclusiveStartKey"] = siguiente

    # --- lecturas de dominio ---

    def leer_comando(self, L: str, command_id: str) -> dict | None:
        return self.obtener(claves.TABLA_OPERACION, claves.comando(L, command_id), claves.SK_CMD)

    def mesa_estructura(self, L: str, mesa_id: str) -> MesaEstructura | None:
        datos = self.obtener(claves.TABLA_CONFIGURACION, L, claves.sk_mesa(mesa_id), consistente=False)
        return MesaEstructura.desde_atributos(datos) if datos else None

    def mesa_estado(self, L: str, mesa_id: str) -> MesaEstado | None:
        datos = self.obtener(claves.TABLA_OPERACION, claves.salon(L), claves.sk_mesa(mesa_id))
        return MesaEstado.desde_atributos(datos) if datos else None

    def pedido(self, L: str, pedido_id: str) -> Pedido | None:
        filas = self.consultar(claves.TABLA_OPERACION, claves.pedido(L, pedido_id))
        cabecera = next((f for f in filas if f["SK"] == claves.SK_PEDIDO), None)
        if cabecera is None:
            return None
        pedido = Pedido.desde_atributos(cabecera)
        pedido.items = [Item.desde_atributos(f) for f in filas if f["SK"].startswith("ITEM#")]
        pedido.pagos = [Pago.desde_atributos(f) for f in filas if f["SK"].startswith("PAGO#")]
        return pedido

    def producto(self, L: str, producto_id: str) -> Producto | None:
        datos = self.obtener(claves.TABLA_CONFIGURACION, L, claves.sk_producto(producto_id), consistente=False)
        return Producto.desde_atributos(datos) if datos else None

    def cuartos(self, L: str) -> dict[str, Cuarto]:
        filas = self.consultar(claves.TABLA_CONFIGURACION, L, prefijo="CUARTO#", consistente=False)
        return {f["cuarto_id"]: Cuarto.desde_atributos(f) for f in filas}

    def impresoras(self, L: str) -> dict[str, Impresora]:
        filas = self.consultar(claves.TABLA_CONFIGURACION, L, prefijo="IMPRESORA#", consistente=False)
        return {f["impresora_id"]: Impresora.desde_atributos(f) for f in filas}

    def config_local(self, L: str) -> ConfigLocal | None:
        datos = self.obtener(claves.TABLA_CONFIGURACION, L, claves.SK_LOCAL, consistente=False)
        return ConfigLocal.desde_atributos(datos) if datos else None

    def turno(self, L: str, turno_id: str) -> Turno | None:
        datos = self.obtener(claves.TABLA_OPERACION, claves.turno(L, turno_id), claves.SK_TURNO)
        return Turno.desde_atributos(datos) if datos else None

    def turno_abierto(self, L: str) -> Turno | None:
        puntero = self.obtener(claves.TABLA_OPERACION, claves.caja(L), claves.SK_TURNO_ABIERTO)
        return self.turno(L, puntero["turno_id"]) if puntero else None

    def membresia(self, sub: str, tenant_id: str, local_id: str) -> Membresia | None:
        datos = self.obtener(claves.TABLA_CONFIGURACION, claves.usuario(sub), claves.sk_membresia(tenant_id, local_id))
        return Membresia.desde_atributos(datos) if datos else None

    def membresias(self, sub: str) -> list[Membresia]:
        filas = self.consultar(claves.TABLA_CONFIGURACION, claves.usuario(sub), prefijo="MEMBRESIA#",
                               consistente=False)
        return [Membresia.desde_atributos(f) for f in filas]

    def identidad(self, sub: str) -> tuple[dict | None, list[Membresia]]:
        filas = self.consultar(claves.TABLA_CONFIGURACION, claves.usuario(sub), consistente=False)
        perfil = next((f for f in filas if f["SK"] == "PERFIL"), None)
        return perfil, [Membresia.desde_atributos(f) for f in filas if f["SK"].startswith("MEMBRESIA#")]

    def email_a_sub(self, email: str) -> str | None:
        datos = self.obtener(claves.TABLA_CONFIGURACION, claves.email(email), "SUB")
        return datos["sub"] if datos else None

    def invitaciones(self, email: str) -> list[dict]:
        return self.consultar(claves.TABLA_CONFIGURACION, claves.invitacion(email), prefijo="MEMBRESIA#")

    def vincular_invitaciones(self, sub: str, email: str, nombre: str) -> tuple[dict | None, list[Membresia]]:
        """Primer ingreso: convierte las invitaciones del email en membresías ligadas al `sub`.

        Una sola transacción, idempotente: si dos peticiones del mismo usuario llegan juntas, la
        segunda falla la condición y simplemente relee lo que dejó la primera."""
        invitaciones = self.invitaciones(email)
        if not invitaciones:
            return None, []
        ahora = tiempo.iso(tiempo.ahora_utc())
        perfil = {"PK": claves.usuario(sub), "SK": "PERFIL", "tipo_item": "PERFIL", "sub": sub, "email": email,
                  "nombre": nombre or email, "estado": "activo", "creado_en": ahora, "version": 1}
        transaccion = [
            self._put(claves.TABLA_CONFIGURACION, perfil, ("no_existe", "PK")),
            self._put(claves.TABLA_CONFIGURACION, {"PK": claves.email(email), "SK": "SUB", "tipo_item": "EMAIL",
                                                   "sub": sub, "email": email}, None),
        ]
        for inv in invitaciones[:40]:
            L = claves.local(inv["tenant_id"], inv["local_id"])
            nombre_miembro = inv.get("nombre") or nombre or email
            membresia = {
                "PK": claves.usuario(sub), "SK": claves.sk_membresia(inv["tenant_id"], inv["local_id"]),
                "tipo_item": "MEMBRESIA", "sub": sub, "tenant_id": inv["tenant_id"], "local_id": inv["local_id"],
                "rol": inv["rol"], "nombre": nombre_miembro, "email": email, "estado": "activo", "version": 1,
                "GSI1PK": claves.gsi_personal(L), "GSI1SK": f"{nombre_miembro}#{sub}", "creado_en": ahora,
            }
            transaccion.append(self._put(claves.TABLA_CONFIGURACION, membresia, None))
            expresion = _Expresion()
            borrar = {"TableName": self.tablas[claves.TABLA_CONFIGURACION],
                      "Key": a_item({"PK": inv["PK"], "SK": inv["SK"]})}
            transaccion.append({"Delete": expresion.aplicar_a(borrar, expresion.condicion(("existe", "PK")))})
        self._simular_falla()
        try:
            self.cliente.transact_write_items(TransactItems=transaccion)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                raise _clasificar_error_cliente(error) from error
            motivos = [m.get("Code", "None") for m in error.response.get("CancellationReasons", [])]
            if any(m not in ("None", "ConditionalCheckFailed") for m in motivos):
                raise _clasificar_cancelacion(motivos, []) from error
        except BotoCoreError as error:
            raise ErrorInfraestructura(f"DynamoDB no respondió: {type(error).__name__}", causa="red") from error
        filas = self.consultar(claves.TABLA_CONFIGURACION, claves.usuario(sub))
        perfil_leido = next((f for f in filas if f["SK"] == "PERFIL"), None)
        return perfil_leido, [Membresia.desde_atributos(f) for f in filas if f["SK"].startswith("MEMBRESIA#")]

    def personal(self, L: str) -> list[dict]:
        return self.consultar(claves.TABLA_CONFIGURACION, claves.gsi_personal(L), indice="GSI1")

    def listar(self, tabla: str, pk: str, prefijo: str | None = None, *, consistente: bool = False) -> list[dict]:
        return self.consultar(tabla, pk, prefijo=prefijo, consistente=consistente)

    def vigilados(self, tipo: str, antes_de: str) -> list[dict]:
        """Ítems del índice disperso GSI1 de `operacion` con GSI1SK menor que `antes_de`."""
        expresion = _Expresion()
        condicion = (f"{expresion.nombre('GSI1PK')} = {expresion.valor(tipo)} AND "
                     f"{expresion.nombre('GSI1SK')} < {expresion.valor(antes_de)}")
        parametros = {"TableName": self.tablas[claves.TABLA_OPERACION], "IndexName": "GSI1",
                      "KeyConditionExpression": condicion, "ExpressionAttributeNames": expresion.nombres,
                      "ExpressionAttributeValues": expresion.valores, "Limit": 200}
        return [desde_item(i) for i in self._llamar("query", **parametros).get("Items", [])]

    def actualizar(self, tabla: str, pk: str, sk: str, *, asignar: dict | None = None, quitar: tuple = (),
                   sumar: dict | None = None, condicion=None, devolver: bool = False) -> dict | None:
        """UpdateItem suelto (no transaccional), para procesos asíncronos y contadores."""
        expresion = _Expresion()
        partes = []
        if asignar:
            partes.append("SET " + ", ".join(f"{expresion.nombre(k)} = {expresion.valor(v)}"
                                              for k, v in asignar.items()))
        if sumar:
            partes.append("ADD " + ", ".join(f"{expresion.nombre(k)} {expresion.valor(v)}" for k, v in sumar.items()))
        if quitar:
            partes.append("REMOVE " + ", ".join(expresion.nombre(k) for k in quitar))
        parametros = {"TableName": self.tablas[tabla], "Key": a_item({"PK": pk, "SK": sk}),
                      "UpdateExpression": " ".join(partes)}
        if devolver:
            parametros["ReturnValues"] = "ALL_NEW"
        expresion.aplicar_a(parametros, expresion.condicion(condicion))
        respuesta = self._llamar("update_item", **parametros)
        return desde_item(respuesta.get("Attributes")) if devolver else None

    def bloqueo(self, L: str, sub: str) -> Bloqueo | None:
        datos = self.obtener(claves.TABLA_OPERACION, claves.autorizaciones(L), claves.sk_bloqueo(sub))
        return Bloqueo.desde_atributos(datos) if datos else None

    def salud(self) -> dict:
        """Lectura mínima de cada tabla (centinela inexistente: 0,5 unidades de lectura)."""
        for tabla in self.tablas:
            self.obtener(tabla, claves.SALUD, claves.SALUD, consistente=False)
        return {"dynamodb": "ok", "zona_horaria": tiempo.fuente_zona()}

    # --- escritura ---

    def _item_cmd(self, ctx, nombre: str, huella: str, http: int, respuesta: dict, estado_cmd: str) -> dict:
        ahora = int(self._reloj())
        return {
            "PK": claves.comando(ctx.L, ctx.command_id), "SK": claves.SK_CMD, "tipo_item": "CMD",
            "command_id": ctx.command_id, "operacion": nombre, "estado": estado_cmd, "http_status": http,
            "respuesta": json.dumps(respuesta, ensure_ascii=False, separators=(",", ":"), default=normalizar),
            "hash_cuerpo": huella, "usuario_id": ctx.usuario_id, "origen": ctx.origen,
            "creado_en": tiempo.iso(tiempo.ahora_utc()), "expira_en": ahora + TTL_CMD,
        }

    def _item_evento(self, ctx, evento: Evento) -> dict:
        event_id = ids.nuevo_ulid()
        return {
            "PK": claves.eventos(ctx.L), "SK": claves.sk_evento(event_id), "tipo_item": "EVT", "event_id": event_id,
            "tipo": evento.tipo, "v": 1, "tenant_id": ctx.tenant_id, "local_id": ctx.local_id,
            "ocurrido_en": ctx.ahora_iso, "registrado_en": tiempo.iso(tiempo.ahora_utc()),
            "usuario_id": ctx.usuario_id, "command_id": ctx.command_id, "origen": ctx.origen,
            "request_id": ctx.request_id, "datos": evento.datos, "expira_en": int(self._reloj()) + TTL_EVT,
        }

    def _put(self, tabla: str, item: dict, condicion) -> dict:
        expresion = _Expresion()
        operacion = {"TableName": self.tablas[tabla], "Item": a_item(item)}
        return {"Put": expresion.aplicar_a(operacion, expresion.condicion(condicion))}

    def _a_transaccion(self, cambio) -> dict:
        clave = {"PK": cambio.pk, "SK": cambio.sk}
        if isinstance(cambio, Guardar):
            atributos = {**cambio.atributos, **clave, "version": cambio.version_leida + 1}
            base = ("no_existe", "PK") if cambio.version_leida == 0 else ("=", "version", cambio.version_leida)
            condicion = ("y", (base, cambio.condicion_extra)) if cambio.condicion_extra else base
            return self._put(cambio.tabla, atributos, condicion)
        if isinstance(cambio, Crear):
            return self._put(cambio.tabla, {**cambio.atributos, **clave}, ("no_existe", "PK"))
        if isinstance(cambio, Reemplazar):
            return self._put(cambio.tabla, {**cambio.atributos, **clave}, ("existe", "PK"))
        if isinstance(cambio, Sumar):
            expresion = _Expresion()
            incrementos = {**cambio.incrementos, "version": 1}
            partes = ["ADD " + ", ".join(f"{expresion.nombre(k)} {expresion.valor(v)}" for k, v in incrementos.items())]
            if cambio.asignar:
                partes.append("SET " + ", ".join(f"{expresion.nombre(k)} = {expresion.valor(v)}"
                                                  for k, v in cambio.asignar.items()))
            operacion = {"TableName": self.tablas[cambio.tabla], "Key": a_item(clave),
                         "UpdateExpression": " ".join(partes)}
            return {"Update": expresion.aplicar_a(operacion, expresion.condicion(cambio.condicion))}
        if isinstance(cambio, Borrar):
            expresion = _Expresion()
            operacion = {"TableName": self.tablas[cambio.tabla], "Key": a_item(clave)}
            return {"Delete": expresion.aplicar_a(operacion, expresion.condicion(cambio.condicion))}
        raise ErrorDeCodigo(f"cambio desconocido: {type(cambio).__name__}")

    def aplicar(self, ctx, nombre: str, huella: str, *, http: int, respuesta: dict, estado_cmd: str,
                cambios: list, eventos: list) -> None:
        item_cmd = self._item_cmd(ctx, nombre, huella, http, respuesta, estado_cmd)
        self._transaccion([self._put(claves.TABLA_OPERACION, item_cmd, ("no_existe", "PK"))], ["cmd"], ctx,
                          cambios, eventos)

    def aplicar_sistema(self, ctx, cambios: list, eventos: list) -> None:
        """Escritura de un proceso asíncrono (sin X-Command-Id): estado + eventos en una transacción."""
        self._transaccion([], [], ctx, cambios, eventos)

    def _transaccion(self, transaccion: list, origenes: list, ctx, cambios: list, eventos: list) -> None:
        for cambio in cambios:
            transaccion.append(self._a_transaccion(cambio))
            origenes.append(cambio)
        for evento in eventos:
            transaccion.append(self._put(claves.TABLA_OPERACION, self._item_evento(ctx, evento), ("no_existe", "PK")))
            origenes.append("evt")
        if len(transaccion) > MAX_ITEMS_TRANSACCION:
            raise ErrorDeCodigo(f"La transacción tiene {len(transaccion)} ítems; el máximo es 100")

        self._simular_falla()
        for intento in range(REINTENTOS_CONFLICTO + 1):
            try:
                self.cliente.transact_write_items(TransactItems=transaccion)
                return
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                    raise _clasificar_error_cliente(error) from error
                motivos = [m.get("Code", "None") for m in error.response.get("CancellationReasons", [])]
                if "TransactionConflict" in motivos and intento < REINTENTOS_CONFLICTO:
                    self._dormir(random.uniform(0.05, 0.2) * (intento + 1))
                    continue
                raise _clasificar_cancelacion(motivos, origenes) from error
            except BotoCoreError as error:
                raise ErrorInfraestructura(f"DynamoDB no respondió: {type(error).__name__}", causa="red") from error

    def guardar_rechazo(self, ctx, nombre: str, huella: str, error: ErrorDominio) -> None:
        """M9: guarda el rechazo como respuesta definitiva del comando. Si falla, no se pierde nada:
        el siguiente reintento simplemente vuelve a evaluar."""
        item = self._item_cmd(ctx, nombre, huella, error.http, error.cuerpo(), "rechazado")
        try:
            self._llamar("put_item", **self._put(claves.TABLA_OPERACION, item, ("no_existe", "PK"))["Put"])
        except (ErrorInfraestructura, ErrorDominio, ErrorDeCodigo) as fallo:
            log.warning("no se guardó el rechazo del comando", extra={"command_id": ctx.command_id,
                                                                      "motivo": type(fallo).__name__})


def _clasificar_error_cliente(error: ClientError) -> Exception:
    codigo = error.response.get("Error", {}).get("Code", "")
    if codigo == "ConditionalCheckFailedException":
        return Conflicto("La operación no se pudo aplicar por un cambio de estado", codigo="CONDICION_NO_CUMPLIDA")
    if codigo == "ValidationException":
        return ErrorDeCodigo(f"DynamoDB rechazó la petición: {error.response.get('Error', {}).get('Message', '')}")
    if codigo in _CODIGOS_INFRA:
        return ErrorInfraestructura(f"DynamoDB: {codigo}", causa=codigo)
    return ErrorInfraestructura(f"DynamoDB: {codigo or 'error desconocido'}", causa=codigo or "desconocido")


def _clasificar_cancelacion(motivos: list[str], origenes: list) -> Exception:
    if any(m in _MOTIVOS_INFRA for m in motivos) or "TransactionConflict" in motivos:
        causa = next(m for m in motivos if m in _MOTIVOS_INFRA | {"TransactionConflict"})
        return ErrorInfraestructura(f"Transacción cancelada: {causa}", causa=causa)
    if "ValidationError" in motivos or "ItemCollectionSizeLimitExceeded" in motivos:
        return ErrorDeCodigo(f"Transacción inválida: {motivos}")
    fallidos = [i for i, motivo in enumerate(motivos) if motivo == "ConditionalCheckFailed"]
    if not fallidos:
        return ErrorInfraestructura(f"Transacción cancelada sin motivo reconocible: {motivos}", causa="desconocido")
    if 0 in fallidos and origenes and origenes[0] == "cmd":
        return ComandoDuplicado()
    origen = origenes[fallidos[0]] if fallidos[0] < len(origenes) else None
    if origen == "evt" or origen is None:
        return Reintentar(None)
    if origen.reintentar:
        return Reintentar(origen.al_fallar)
    return origen.al_fallar or Conflicto("La operación no se pudo aplicar por un cambio de estado",
                                         codigo="CONDICION_NO_CUMPLIDA")
