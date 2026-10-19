"""Genera eventos-prueba/: eventos para el botón «Probar» de la consola de Lambda, con los datos mock
de la herramienta `semilla` (cliente demo, local local_01, personas mock-*).

Solo biblioteca estándar. Uso: python scripts/generar_eventos_prueba.py

Las funciones leen la identidad desde el evento (requestContext.authorizer.jwt.claims), así que
estos eventos prueban todo el backend sin Google y sin el API Gateway. Cada escritura lleva un
X-Command-Id fijo: si repites un evento, la función devuelve la respuesta guardada (idempotencia);
para volver a ejecutarlo de verdad, cambia el X-Command-Id.

FLUJO define el orden recomendado y el código HTTP esperado. tests/funciones/test_eventos_prueba.py
lo ejecuta completo contra el entorno simulado.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "eventos-prueba"
TENANT, LOCAL = "demo", "local_01"
_ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def fijo(n: int) -> str:
    """ULID fijo y válido para los eventos (los mismos en cada generación)."""
    return "01K7H0Z3Q8W4M2N5P6R7S8T9" + _ALFABETO[n // 32] + _ALFABETO[n % 32]


PEDIDO, ITEM_PIZZA, ITEM_BEBIDA, PEDIDO_CONTINGENCIA = fijo(900), fijo(901), fijo(902), fijo(903)
L = {"local_id": LOCAL}
P = {**L, "pedido_id": PEDIDO}
T = {**L, "turno_id": "REEMPLAZAR_TURNO_ID"}
IMPRESORA = {"tenant_id": TENANT, "local_id": LOCAL, "impresora_id": "imp_cocina"}
BASIC_COCINA = {"authorization": "Basic " + base64.b64encode(b"imp_cocina:mock-clave-cocina").decode()}


def http(route_key: str, parametros: dict | None = None, cuerpo: dict | None = None, *, sub: str | None = "mock-garzon",
         command_id: str | None = None, query: dict | None = None, encabezados: dict | None = None) -> dict:
    metodo, ruta = route_key.split(" ", 1)
    headers = {"content-type": "application/json", **(encabezados or {})}
    if command_id:
        headers["x-command-id"] = command_id
    contexto = {"requestId": "prueba-consola", "routeKey": route_key,
                "http": {"method": metodo, "path": ruta, "sourceIp": "203.0.113.10"}}
    if sub:
        contexto["authorizer"] = {"jwt": {"claims": {
            "sub": sub, "email": f"{sub}@demo.invalid", "email_verified": "true", "name": sub,
            "iss": "https://accounts.google.com"}, "scopes": None}}
    return {"version": "2.0", "routeKey": route_key, "rawPath": ruta, "headers": headers,
            "pathParameters": parametros or {}, "queryStringParameters": query, "requestContext": contexto,
            "body": json.dumps(cuerpo, ensure_ascii=False) if cuerpo is not None else None, "isBase64Encoded": False}


def sqs(cuerpo: dict, *, fifo: bool = False) -> dict:
    atributos = {"ApproximateReceiveCount": "1", "SentTimestamp": "1760000000000"}
    if fifo:
        atributos.update({"MessageGroupId": f"{LOCAL}#m07", "MessageDeduplicationId": cuerpo.get("command_id", "")})
    return {"Records": [{"messageId": "prueba-1", "receiptHandle": "prueba", "body": json.dumps(cuerpo),
                         "attributes": atributos, "eventSource": "aws:sqs"}]}


# (función, archivo, evento, código HTTP esperado o None si no es HTTP, qué comprobar)
FLUJO = [
    ("salon", "01-salud", http("GET /salud", sub=None), 200, "DynamoDB responde"),
    ("salon", "02-yo", http("GET /yo"), 200, "mock-garzon es garzon en MISE Centro"),
    ("salon", "03-plano", http("GET /locales/{local_id}/salon", L), 200, "12 mesas, todas libres"),
    ("salon", "04-catalogo", http("GET /locales/{local_id}/catalogo", L), 200, "10 productos"),
    ("pedidos", "01-abrir-mesa", http("POST /locales/{local_id}/pedidos", L, {"mesa_id": "m05", "pedido_id": PEDIDO},
                                      command_id=fijo(1)), 201, f"pedido {PEDIDO} en la mesa 5"),
    ("pedidos", "02-agregar-pizza-xl", http("POST /locales/{local_id}/pedidos/{pedido_id}/items", P,
                                            {"producto_id": "pizza", "modificador_id": "xl", "item_id": ITEM_PIZZA,
                                             "observacion": "sin aceitunas", "mesa_id": "m05"}, command_id=fijo(2)),
     201, "precio congelado 12.900"),
    ("pedidos", "03-agregar-bebidas", http("POST /locales/{local_id}/pedidos/{pedido_id}/items", P,
                                           {"producto_id": "bebida", "cantidad": 2, "item_id": ITEM_BEBIDA,
                                            "mesa_id": "m05"}, command_id=fijo(3)), 201, "subtotal 3.600"),
    ("pedidos", "04-enviar-tanda", http("POST /locales/{local_id}/pedidos/{pedido_id}/enviar", P, {"mesa_id": "m05"},
                                        command_id=fijo(4)), 200, "tanda 1; Cocina y Barra: encolada"),
    ("pedidos", "05-ver-pedido", http("GET /locales/{local_id}/pedidos/{pedido_id}", P), 200, "total 16.500"),
    ("pedidos", "06-precuenta", http("POST /locales/{local_id}/pedidos/{pedido_id}/precuenta", P, {"mesa_id": "m05"},
                                     command_id=fijo(5)), 200, "pedido y mesa en precuenta"),
    ("pedidos", "07-reabrir-sin-confirmar", http("POST /locales/{local_id}/pedidos/{pedido_id}/reabrir", P,
                                                 {"mesa_id": "m05"}, command_id=fijo(6)),
     422, "CONFIRMACION_REQUERIDA (M13)"),
    ("salon", "05-bloquear-mesa", http("POST /locales/{local_id}/mesas/{mesa_id}/bloqueo", {**L, "mesa_id": "m12"},
                                       {"bloqueada": True}, sub="mock-cajero", command_id=fijo(10)), 200,
     "mesa 12 bloqueada"),
    ("impresion", "01-consulta-cocina", http("POST /impresion/{tenant_id}/{local_id}/{impresora_id}", IMPRESORA,
                                             {"status": "200 OK"}, sub=None, encabezados=BASIC_COCINA), 200,
     "jobReady: true; copia el jobToken"),
    ("impresion", "02-descargar", http("GET /impresion/{tenant_id}/{local_id}/{impresora_id}", IMPRESORA, sub=None,
                                       query={"token": "REEMPLAZAR_TRABAJO_ID", "type": "text/plain"},
                                       encabezados=BASIC_COCINA), 200, "texto de la comanda de cocina"),
    ("impresion", "03-confirmar", http("DELETE /impresion/{tenant_id}/{local_id}/{impresora_id}", IMPRESORA, sub=None,
                                       query={"token": "REEMPLAZAR_TRABAJO_ID", "code": "200 OK"},
                                       encabezados=BASIC_COCINA), 200, "confirmado: true"),
    ("caja", "01-abrir-turno", http("POST /locales/{local_id}/caja/turnos", L, {"monto_apertura": 50000},
                                    sub="mock-cajero", command_id=fijo(20)), 201, "copia el turno_id"),
    ("caja", "02-turno-actual", http("GET /locales/{local_id}/caja/turno", L, sub="mock-cajero"), 200,
     "sin totales (arqueo ciego)"),
    ("caja", "03-pendientes", http("GET /locales/{local_id}/caja/pendientes", L, sub="mock-cajero"), 200,
     "la mesa 5 por cobrar"),
    ("caja", "04-pagar", http("POST /locales/{local_id}/pedidos/{pedido_id}/pagos", P, {"medios": [
        {"metodo": "efectivo", "monto": 16500, "propina": 1650, "efectivo_recibido": 20000}]},
        sub="mock-cajero", command_id=fijo(21)), 201, "vuelto 1.850, saldo 0"),
    ("caja", "05-finalizar-boleta", http("POST /locales/{local_id}/pedidos/{pedido_id}/finalizar", P,
                                         {"tipo_documento": "boleta"}, sub="mock-cajero", command_id=fijo(22)), 200,
     "documento pendiente; la mesa 5 queda libre"),
    ("caja", "06-documento", http("GET /locales/{local_id}/caja/documentos/{venta_id}", {**L, "venta_id": PEDIDO},
                                  sub="mock-cajero"), 200, "pendiente, y en segundos emitido con folio"),
    ("caja", "07-autorizadores", http("GET /locales/{local_id}/caja/autorizadores", L, sub="mock-cajero"), 200,
     "mock-dueno y mock-admin"),
    ("caja", "08-retiro", http("POST /locales/{local_id}/caja/retiros", L, {
        "monto": 5000, "motivo": "Compra de hielo", "autorizador_id": "mock-admin", "codigo": "4321"},
        sub="mock-cajero", command_id=fijo(23)), 201, "autorizado por mock-admin"),
    ("caja", "09-retiro-codigo-incorrecto", http("POST /locales/{local_id}/caja/retiros", L, {
        "monto": 5000, "motivo": "Prueba", "autorizador_id": "mock-admin", "codigo": "0000"},
        sub="mock-cajero", command_id=fijo(24)), 403, "CODIGO_AUTORIZACION_INVALIDO, 4 intentos restantes"),
    ("caja", "10-conteo", http("POST /locales/{local_id}/caja/turnos/{turno_id}/conteo", T, {"monto": 63150},
                               sub="mock-cajero", command_id=fijo(25)), 200,
     "conteo_completado: true (50.000 + 18.150 − 5.000)"),
    ("caja", "11-conciliacion", http("POST /locales/{local_id}/caja/turnos/{turno_id}/conciliacion", T,
                                     {"total_debito_pos": 0, "total_credito_pos": 0}, sub="mock-cajero",
                                     command_id=fijo(26)), 200, "conciliación registrada"),
    ("caja", "12-cerrar-turno", http("POST /locales/{local_id}/caja/turnos/{turno_id}/cerrar", T, {}, sub="mock-cajero",
                                     command_id=fijo(27)), 200, "diferencia_efectivo: 0"),
    ("reportes", "01-turnos", http("GET /locales/{local_id}/reportes/turnos", L, sub="mock-dueno"), 200,
     "el turno cerrado"),
    ("reportes", "02-turno", http("GET /locales/{local_id}/reportes/turnos/{turno_id}", T, sub="mock-dueno"), 200,
     "caja y, en segundos, resumen con 1 venta"),
    ("administracion", "01-listar-productos", http("GET /locales/{local_id}/admin/{recurso}", {**L, "recurso": "productos"},
                                                   sub="mock-admin"), 200, "10 productos"),
    ("administracion", "02-crear-sector", http("POST /locales/{local_id}/admin/{recurso}", {**L, "recurso": "sectores"},
                                               {"nombre": "Barra exterior"}, sub="mock-admin", command_id=fijo(30)),
     201, "sector nuevo"),
    ("administracion", "03-sector-duplicado", http("POST /locales/{local_id}/admin/{recurso}",
                                                   {**L, "recurso": "sectores"}, {"nombre": "  terraza "},
                                                   sub="mock-admin", command_id=fijo(31)), 409, "DUPLICADO"),
    ("administracion", "04-listar-personal", http("GET /locales/{local_id}/admin/{recurso}", {**L, "recurso": "personal"},
                                                  sub="mock-admin"), 200, "6 personas mock"),
    ("administracion", "05-ver-configuracion", http("GET /locales/{local_id}/admin/{recurso}",
                                                    {**L, "recurso": "configuracion"}, sub="mock-admin"), 200,
     "umbral 2 %, mínimo 5.000"),
    ("contingencia", "01-comanda", http("POST /contingencia/comandas", None, {
        "operacion": "pedido.abrir", "local_id": LOCAL, "cuerpo": {"mesa_id": "m07", "pedido_id": PEDIDO_CONTINGENCIA}},
        command_id=fijo(40)), 202, "aceptada_en_contingencia (queda en la cola FIFO)"),
    ("drenador-contingencia", "01-abrir-mesa-m07", sqs({
        "v": 1, "operacion": "pedido.abrir", "local_id": LOCAL, "grupo": f"{LOCAL}#m07",
        "cuerpo": {"mesa_id": "m07", "pedido_id": PEDIDO_CONTINGENCIA}, "command_id": fijo(40), "sub": "mock-garzon",
        "email": "mock-garzon@demo.invalid", "nombre": "mock-garzon", "ocurrido_en": "2026-10-15T20:00:00.000Z",
        "entrada": "cliente"}, fifo=True), None, 'batchItemFailures: []; la mesa 7 queda ocupada con origen "contingencia"'),
    ("drenador-contingencia", "02-agregar-a-mesa-ya-cobrada", sqs({
        "v": 1, "operacion": "pedido.agregar_item", "local_id": LOCAL, "grupo": f"{LOCAL}#m05",
        "cuerpo": {"mesa_id": "m05", "pedido_id": PEDIDO, "producto_id": "cafe"}, "command_id": fijo(42),
        "sub": "mock-garzon", "email": "mock-garzon@demo.invalid", "nombre": "mock-garzon",
        "ocurrido_en": "2026-10-15T20:05:00.000Z", "entrada": "cliente"}, fifo=True), None,
     "batchItemFailures: [] (no se reintenta); queda un CONFLICTO# y llega un correo al dueño"),
    ("caja", "13-conflictos", http("GET /locales/{local_id}/caja/conflictos", L, sub="mock-cajero"), 200,
     "un conflicto PEDIDO_CERRADO de la mesa 5"),
    ("emision-dte", "01-mensaje", sqs({"tenant_id": TENANT, "local_id": LOCAL, "turno_id": "REEMPLAZAR_TURNO_ID",
                                      "venta_id": PEDIDO}), None, "batchItemFailures: [] (si ya estaba emitido, no hace nada)"),
    ("procesador-eventos", "01-registro-no-evento", {"Records": [{
        "eventID": "1", "eventName": "INSERT", "eventSource": "aws:dynamodb",
        "dynamodb": {"SequenceNumber": "1", "Keys": {"PK": {"S": "x"}, "SK": {"S": "y"}},
                     "NewImage": {"PK": {"S": "x"}, "SK": {"S": "y"}, "tipo_item": {"S": "PEDIDO"}}}}]},
     None, "batchItemFailures: [] (lo descarta: no es un evento)"),
    ("tareas-programadas", "01-regla-eventbridge", {
        "version": "0", "id": "prueba", "detail-type": "Scheduled Event", "source": "aws.events",
        "account": "123456789012", "time": "2026-10-15T20:00:00Z", "region": "us-east-1",
        "resources": ["arn:aws:events:us-east-1:123456789012:rule/pos-tareas-programadas"], "detail": {}},
     None, "conteos de lo reencolado y avisado"),
    ("reservas", "01-disponibilidad", http("GET /publico/{tenant_id}/{local_id}/reservas/disponibilidad",
                                           {"tenant_id": TENANT, "local_id": LOCAL}, sub=None), 501,
     "NO_IMPLEMENTADO (esqueleto)"),
    ("pedidos-externos", "01-webhook-firma-invalida", http("POST /webhooks/{plataforma}/{tenant_id}/{local_id}",
                                                           {"plataforma": "demo", "tenant_id": TENANT, "local_id": LOCAL},
                                                           {"pedido": 1}, sub=None, encabezados={"x-firma": "invalida"}),
     401, "FIRMA_INVALIDA"),
]


def main() -> None:
    for archivo in DESTINO.rglob("*.json"):
        archivo.unlink()
    lineas = ["# Eventos de prueba", "",
              "Generado por `scripts/generar_eventos_prueba.py`. No editar a mano.", "",
              "Requisitos: la herramienta `semilla` ya ejecutada (datos mock). En la consola de Lambda: función → "
              "pestaña **Test** → **Create new event** → pega el JSON → **Test**.", "",
              "Reemplaza `REEMPLAZAR_TURNO_ID` por el `turno_id` que devuelve `caja/01-abrir-turno`, y "
              "`REEMPLAZAR_TRABAJO_ID` por el `jobToken` de `impresion/01-consulta-cocina`.", "",
              "Repetir un evento de escritura devuelve la respuesta guardada (idempotencia). Para ejecutarlo de nuevo de "
              "verdad, cambia su `x-command-id` por otro ULID.", "",
              "| Orden | Función | Evento | HTTP esperado | Qué comprobar |", "|---|---|---|---|---|"]
    for orden, (funcion, nombre, evento, esperado, comprobar) in enumerate(FLUJO, start=1):
        carpeta = DESTINO / funcion
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"{nombre}.json").write_text(json.dumps(evento, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lineas.append(f"| {orden} | `{funcion}` | `{nombre}.json` | {esperado or '—'} | {comprobar} |")
    (DESTINO / "README.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{len(FLUJO)} eventos en {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
