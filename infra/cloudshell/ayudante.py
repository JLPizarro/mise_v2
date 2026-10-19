"""Genera los archivos JSON que usa desplegar.sh, para no armar JSON anidado a mano en bash.

Solo biblioteca estándar. Subcomandos:
  atributos ARCHIVO CLAVE=VALOR ...           objeto de textos (atributos de SQS)
  redrive ARN MAXIMO                          imprime el valor de RedrivePolicy
  variables ARCHIVO CLAVE=VALOR ...           {"Variables": {...}} para Lambda
  filtro_streams ARCHIVO                      filtro del disparador: solo inserciones de EVT#
  destino_fallo ARCHIVO ARN_COLA              destino ante fallo del disparador de Streams
  registro_acceso ARCHIVO ARN_GRUPO           configuración del registro de acceso del stage
  limites_rutas ARCHIVO                       límites de tasa por ruta (/publico, /impresion, /webhooks)
  jwt ARCHIVO AUDIENCIA EMISOR                configuración del autorizador
  cors ARCHIVO ORIGEN [ORIGEN ...]            CORS de la API
  alarma_5xx ARCHIVO API_ID                   métricas para la alarma de porcentaje de 5xx
  sentencias_sql ARCHIVO_SQL BUCKET DESTINO   separa el .sql de Athena en archivos 1.sql, 2.sql...
  buscar ARCHIVO CAMPO VALOR SALIDA           en {"Items": [...]}, imprime SALIDA del ítem con CAMPO == VALOR
  canales                                     colas del catálogo central (pos_dominio/mensajeria.py), una por
                                              línea: id, nombre, fifo, visibilidad, recepciones, fallidos
                                              (primero las colas de fallidos, que las demás referencian)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lambdas" / "capa" / "python"))


def _pares(argumentos: list[str]) -> dict[str, str]:
    return dict(a.split("=", 1) for a in argumentos)


def _escribir(archivo: str, datos) -> None:
    Path(archivo).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def main(args: list[str]) -> int:
    orden, resto = args[0], args[1:]
    if orden == "atributos":
        _escribir(resto[0], _pares(resto[1:]))
    elif orden == "redrive":
        print(json.dumps({"deadLetterTargetArn": resto[0], "maxReceiveCount": resto[1]}))
    elif orden == "variables":
        _escribir(resto[0], {"Variables": _pares(resto[1:])})
    elif orden == "filtro_streams":
        patron = {"eventName": ["INSERT"], "dynamodb": {"Keys": {"SK": {"S": [{"prefix": "EVT#"}]}}}}
        _escribir(resto[0], {"Filters": [{"Pattern": json.dumps(patron, separators=(",", ":"))}]})
    elif orden == "destino_fallo":
        _escribir(resto[0], {"OnFailure": {"Destination": resto[1]}})
    elif orden == "registro_acceso":
        formato = {"requestId": "$context.requestId", "routeKey": "$context.routeKey", "status": "$context.status",
                   "integrationErrorMessage": "$context.integrationErrorMessage",
                   "authorizerError": "$context.authorizer.error", "responseLatency": "$context.responseLatency",
                   "integrationLatency": "$context.integrationLatency", "ip": "$context.identity.sourceIp",
                   "requestTime": "$context.requestTime"}
        _escribir(resto[0], {"DestinationArn": resto[1], "Format": json.dumps(formato, separators=(",", ":"))})
    elif orden == "limites_rutas":
        from rutas_api import rutas

        limites = {}
        for metodo, ruta, _, _ in rutas():
            clave = f"{metodo} {ruta}"
            if ruta.startswith("/publico/"):
                limites[clave] = {"ThrottlingRateLimit": 2, "ThrottlingBurstLimit": 5}
            elif ruta.startswith("/impresion/"):
                limites[clave] = {"ThrottlingRateLimit": 20, "ThrottlingBurstLimit": 40}
            elif ruta.startswith("/webhooks/"):
                limites[clave] = {"ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 10}
        _escribir(resto[0], limites)
    elif orden == "jwt":
        _escribir(resto[0], {"Audience": [resto[1]], "Issuer": resto[2]})
    elif orden == "cors":
        _escribir(resto[0], {"AllowOrigins": resto[1:], "AllowHeaders": ["authorization", "content-type", "x-command-id"],
                             "AllowMethods": ["GET", "POST", "PATCH", "DELETE"], "ExposeHeaders": ["x-comando-repetido"],
                             "MaxAge": 600, "AllowCredentials": False})
    elif orden == "alarma_5xx":
        dimensiones = [{"Name": "ApiId", "Value": resto[1]}, {"Name": "Stage", "Value": "prod"}]
        _escribir(resto[0], [
            {"Id": "m1", "ReturnData": False, "MetricStat": {"Stat": "Sum", "Period": 300, "Metric": {
                "Namespace": "AWS/ApiGateway", "MetricName": "5xx", "Dimensions": dimensiones}}},
            {"Id": "m2", "ReturnData": False, "MetricStat": {"Stat": "Sum", "Period": 300, "Metric": {
                "Namespace": "AWS/ApiGateway", "MetricName": "Count", "Dimensions": dimensiones}}},
            {"Id": "e1", "ReturnData": True, "Label": "porcentaje de respuestas 5xx",
             "Expression": "IF(m2 > 0, 100 * m1 / m2, 0)"},
        ])
    elif orden == "sentencias_sql":
        texto = Path(resto[0]).read_text(encoding="utf-8").replace("<BUCKET_ARCHIVO>", resto[1])
        sin_comentarios = "\n".join(l for l in texto.splitlines() if not l.strip().startswith("--"))
        sentencias = [s.strip() for s in re.split(r";\s*(?:\n|$)", sin_comentarios) if s.strip()]
        destino = Path(resto[2])
        destino.mkdir(parents=True, exist_ok=True)
        for i, sentencia in enumerate(sentencias, start=1):
            (destino / f"{i}.sql").write_text(sentencia, encoding="utf-8")
        print(len(sentencias))
    elif orden == "buscar":
        items = json.loads(Path(resto[0]).read_text(encoding="utf-8")).get("Items", [])
        print(next((i[resto[3]] for i in items if i.get(resto[1]) == resto[2]), ""))
    elif orden == "canales":
        from pos_dominio.mensajeria import CANALES

        colas = [c for c in CANALES.values() if c.tipo in ("cola_fallidos", "cola")]
        for c in sorted(colas, key=lambda c: c.tipo != "cola_fallidos"):
            print("	".join([c.id, c.nombre_aws, "si" if c.fifo else "no", str(c.visibilidad),
                             str(c.max_recepciones or "-"), c.fallidos or "-"]))
    else:
        print(f"subcomando desconocido: {orden}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
