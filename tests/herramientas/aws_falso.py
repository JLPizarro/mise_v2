"""AWS CLI falsa para probar infra/cloudshell/desplegar.sh sin AWS.

Responde lo mínimo que el script necesita, registra cada llamada en AWS_FALSO_LOG y falla si un
argumento file://… no existe o no es JSON válido (fileb:// debe existir). Con AWS_FALSO_EXISTE=1
simula una re-ejecución: todo ya existe y el script debe tomar el camino de actualización.
"""

import json
import os
import sys
from pathlib import Path

CUENTA = "123456789012"
EXISTE = os.environ.get("AWS_FALSO_EXISTE") == "1"
RUTAS_EXISTENTES_DOC = Path(__file__).parents[2] / "docs" / "migracion" / "02-api-gateway.md"


def salir(texto: str = "", codigo: int = 0) -> None:
    if texto:
        print(texto)
    sys.exit(codigo)


def main(args: list[str]) -> None:
    with open(os.environ["AWS_FALSO_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    for i, arg in enumerate(args):
        for prefijo in ("file://", "fileb://"):
            if arg.startswith(prefijo):
                ruta = Path(arg[len(prefijo):])
                if not ruta.exists():
                    salir(f"archivo inexistente: {ruta}", 255)
                if prefijo == "file://":
                    try:
                        json.loads(ruta.read_text(encoding="utf-8"))
                    except ValueError as error:
                        salir(f"JSON inválido en {ruta}: {error}", 255)
    servicio, orden = args[0], args[1] if len(args) > 1 else ""
    if servicio == "s3" and orden == "cp" and os.environ.get("AWS_FALSO_COPIAS") and args[3].startswith("s3://"):
        # Guarda lo que se sube, para que una prueba pueda comprobar su contenido (p. ej. config.json).
        destino = Path(os.environ["AWS_FALSO_COPIAS"]) / args[3].split("/", 3)[3]
        destino.parent.mkdir(parents=True, exist_ok=True)
        origen = Path(args[2])
        if not origen.exists():  # ruta de MSYS (/tmp/...) vista desde un Python de Windows
            import subprocess

            origen = Path(subprocess.run(["cygpath", "-w", args[2]], capture_output=True, text=True, check=True).stdout.strip())
        destino.write_bytes(origen.read_bytes())
    consulta = args[args.index("--query") + 1] if "--query" in args else ""

    def valor(opcion: str) -> str:
        return args[args.index(opcion) + 1] if opcion in args else ""

    if (servicio, orden) == ("sts", "get-caller-identity"):
        salir(CUENTA)
    if servicio == "lambda" and orden == "get-account-settings":
        salir("1000")
    if servicio == "s3api" and orden == "head-bucket":
        salir(codigo=0 if EXISTE else 1)
    if servicio == "dynamodb" and orden == "describe-table":
        if "IndexStatus" in consulta:
            # AWS_FALSO_SIN_GSI=1: la tabla existe sin GSI1 hasta que el script lo crea con update-table.
            creado = any(json.loads(l)[:2] == ["dynamodb", "update-table"] and valor("--table-name") in l
                         and "--global-secondary-index-updates" in l
                         for l in Path(os.environ["AWS_FALSO_LOG"]).read_text(encoding="utf-8").splitlines())
            salir("None" if os.environ.get("AWS_FALSO_SIN_GSI") == "1" and not creado else "ACTIVE")
        if "StreamViewType" in consulta:
            salir("NEW_IMAGE")
        if "LatestStreamArn" in consulta:
            salir(f"arn:aws:dynamodb:us-east-1:{CUENTA}:table/operacion/stream/2026-10-16T00:00:00.000")
        salir(codigo=0 if EXISTE else 1)
    if servicio == "dynamodb" and orden == "describe-time-to-live":
        salir("ENABLED" if EXISTE else "DISABLED")
    if servicio == "sqs" and orden == "get-queue-url":
        if EXISTE:
            salir(f"https://sqs.us-east-1.amazonaws.com/{CUENTA}/{valor('--queue-name')}")
        salir("QueueDoesNotExist", 254)
    if servicio == "sqs" and orden == "create-queue":
        salir(f"https://sqs.us-east-1.amazonaws.com/{CUENTA}/{valor('--queue-name')}")
    if servicio == "sqs" and orden == "get-queue-attributes":
        salir(f"arn:aws:sqs:us-east-1:{CUENTA}:{valor('--queue-url').rsplit('/', 1)[-1]}")
    if servicio == "sns" and orden == "create-topic":
        salir(f"arn:aws:sns:us-east-1:{CUENTA}:{valor('--name')}")
    if servicio == "logs" and orden == "describe-log-groups":
        salir(f"arn:aws:logs:us-east-1:{CUENTA}:log-group:/aws/apigateway/pos-api:*")
    if servicio == "lambda" and orden == "publish-layer-version":
        salir(f"arn:aws:lambda:us-east-1:{CUENTA}:layer:pos-dominio:7")
    if servicio == "lambda" and orden == "get-function-configuration":
        salir("secreto-existente" if EXISTE else "None")
    if servicio == "lambda" and orden == "get-function":
        salir(codigo=0 if EXISTE else 255)
    if servicio == "lambda" and orden == "publish-version":
        salir("4" if EXISTE else "1")
    if servicio == "lambda" and orden == "get-alias":
        if EXISTE:
            salir("3")
        salir("ResourceNotFoundException", 254)
    if servicio == "lambda" and orden == "list-event-source-mappings":
        salir("uuid-existente" if EXISTE else "None")
    if servicio == "lambda" and orden == "invoke":
        Path(args[-1]).write_text(json.dumps({"creados": 110, "ya_existian": 0}), encoding="utf-8")
        salir(json.dumps({"StatusCode": 200}))
    if servicio == "events" and orden == "put-rule":
        salir(f"arn:aws:events:us-east-1:{CUENTA}:rule/pos-tareas-programadas")
    if servicio == "apigatewayv2" and orden == "get-apis":
        salir("abc123" if EXISTE else "None")
    if servicio == "apigatewayv2" and orden == "create-api":
        salir("abc123")
    if servicio == "apigatewayv2" and orden == "get-authorizers":
        salir("auth1" if EXISTE else "None")
    if servicio == "apigatewayv2" and orden == "create-authorizer":
        salir("auth1")
    if servicio == "apigatewayv2" and orden == "get-integrations":
        if EXISTE:
            items = [{"IntegrationUri": f"arn:aws:lambda:us-east-1:{CUENTA}:function:{f}:vivo", "IntegrationId": f"int-{f}"}
                     for f in ("salon", "pedidos", "caja", "administracion", "reportes", "impresion", "contingencia",
                               "reservas", "pedidos-externos", "mensajeria")]
            salir(json.dumps({"Items": items}))
        salir(json.dumps({"Items": []}))
    if servicio == "apigatewayv2" and orden == "create-integration":
        salir(f"int-{valor('--integration-uri').split(':')[-2]}")
    if servicio == "apigatewayv2" and orden == "get-routes":
        sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
        from rutas_api import rutas

        items = [{"RouteKey": f"{m} {r}", "RouteId": f"ruta-{i}"} for i, (m, r, _, _) in enumerate(rutas())] if EXISTE else []
        salir(json.dumps({"Items": items}))
    if servicio == "apigatewayv2" and orden == "get-stage":
        salir(codigo=0 if EXISTE else 255)
    if servicio == "athena" and orden == "start-query-execution":
        salir("consulta-1")
    if servicio == "athena" and orden == "get-query-execution":
        salir("SUCCEEDED")
    # create-*, update-*, put-*, wait, delete, add-permission, s3 cp, subscribe...: éxito sin salida
    salir()


if __name__ == "__main__":
    main(sys.argv[1:])
