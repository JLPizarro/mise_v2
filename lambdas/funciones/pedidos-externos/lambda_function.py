"""Función `pedidos-externos`: webhook de plataformas de delivery. ESQUELETO, sin reglas de negocio.

El POS local no recibía pedidos de plataformas y no existe el concepto de pedido sin mesa. Por
decisión del equipo (P3) queda para después; falta definir plataforma y formato (pregunta P13).

Lo que sí queda resuelto y probado: la verificación de la firma.
- Encabezado X-Firma con HMAC-SHA256 del cuerpo crudo (hex), con el secreto de SECRETO_WEBHOOK.
- Comparación en tiempo constante. Sin firma válida: 401, sin leer el cuerpo.
- En producción el secreto iría en un gestor de secretos (AWS Secrets Manager o Parameter Store),
  leído al arrancar y con rotación; aquí va en una variable de entorno porque el Learner Lab es
  temporal y Secrets Manager cuesta por secreto.

Manejador: lambda_function.lambda_handler
Variables: SECRETO_WEBHOOK, TABLA_CONFIGURACION, TABLA_OPERACION, LOG_LEVEL (opcional)
"""

import hashlib
import hmac
import os

from pos_dominio import claves
from pos_dominio.errores import ErrorDominio, NoAutenticado
from pos_dominio.infra import aws, http

aws.exigir_entorno("SECRETO_WEBHOOK", "TABLA_OPERACION", "TABLA_CONFIGURACION")
app = http.Aplicacion("pedidos-externos")


class NoImplementado(ErrorDominio):
    http = 501
    codigo = "NO_IMPLEMENTADO"


def firma_valida(cuerpo: bytes, firma: str | None, secreto: str) -> bool:
    if not firma:
        return False
    esperada = hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma.strip().lower())


@app.ruta("POST /webhooks/{plataforma}/{tenant_id}/{local_id}", publica=True)
def recibir(peticion):
    if not firma_valida(peticion.cuerpo_bytes, peticion.encabezados.get("x-firma"), os.environ["SECRETO_WEBHOOK"]):
        raise NoAutenticado("Firma inválida", codigo="FIRMA_INVALIDA")
    claves.local(peticion.parametros.get("tenant_id"), peticion.parametros.get("local_id"))
    claves.validar_id(peticion.parametros.get("plataforma"), "plataforma")
    raise NoImplementado("La integración con plataformas de delivery aún no está disponible")


lambda_handler = app
