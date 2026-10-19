"""Logs en JSON con la biblioteca estándar.

- Nivel por defecto WARNING (variable LOG_LEVEL para cambiarlo).
- Campos de correlación: requestId, command_id, tenant_id, event_id, que se agregan con
  `correlacion(...)` y quedan en todos los registros de esa invocación.
- Nunca se registran el encabezado Authorization, tokens, códigos de autorización ni claves de
  impresora: cualquier campo con esos nombres se reemplaza por "[oculto]".
"""

import contextvars
import json
import logging
import os
import time

_CONTEXTO: contextvars.ContextVar[dict] = contextvars.ContextVar("pos_log", default={})
_ESTANDAR = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}
_SUBCADENAS_SENSIBLES = ("authorization", "token", "secret", "secreto", "password", "clave", "firma", "signature",
                         "cookie")


def _sensible(clave: str) -> bool:
    clave = clave.lower()
    return clave.startswith("codigo") or clave in ("pin", "pin_hash", "pin_sal") or \
        any(s in clave for s in _SUBCADENAS_SENSIBLES)


def ocultar(valor):
    if isinstance(valor, dict):
        return {k: "[oculto]" if _sensible(str(k)) else ocultar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [ocultar(v) for v in valor]
    return valor


class FormatoJSON(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        datos = {
            "momento": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(registro.created)) + f".{int(registro.msecs):03d}Z",
            "nivel": registro.levelname,
            "logger": registro.name,
            "mensaje": registro.getMessage(),
            **_CONTEXTO.get(),
        }
        for clave, valor in registro.__dict__.items():
            if clave not in _ESTANDAR and not clave.startswith("_"):
                datos[clave] = valor
        if registro.exc_info:
            datos["excepcion"] = self.formatException(registro.exc_info)
        return json.dumps(ocultar(datos), ensure_ascii=False, default=str)


def configurar() -> None:
    raiz = logging.getLogger()
    raiz.setLevel(os.environ.get("LOG_LEVEL", "WARNING").upper())
    if not raiz.handlers:
        raiz.addHandler(logging.StreamHandler())
    for manejador in raiz.handlers:
        if not isinstance(manejador.formatter, FormatoJSON):
            manejador.setFormatter(FormatoJSON())
    # boto3 registra a nivel DEBUG con datos de la petición; se deja en WARNING siempre.
    for nombre in ("boto3", "botocore", "urllib3"):
        logging.getLogger(nombre).setLevel(logging.WARNING)


def correlacion(**campos) -> None:
    _CONTEXTO.set({**_CONTEXTO.get(), **{k: v for k, v in campos.items() if v}})


def limpiar_correlacion() -> None:
    _CONTEXTO.set({})
