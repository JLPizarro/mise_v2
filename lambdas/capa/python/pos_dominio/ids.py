"""ULID con la biblioteca estándar: 48 bits de milisegundos + 80 bits aleatorios, en Crockford base32.

Son ordenables por tiempo, así que sirven como clave de orden (EVT#, ITEM#, TURNO#...)."""

import re
import secrets
import time

_ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_PATRON = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")


def _codificar(valor: int, largo: int) -> str:
    caracteres = []
    for _ in range(largo):
        caracteres.append(_ALFABETO[valor & 31])
        valor >>= 5
    return "".join(reversed(caracteres))


def nuevo_ulid(milisegundos: int | None = None) -> str:
    if milisegundos is None:
        milisegundos = time.time_ns() // 1_000_000
    return _codificar(milisegundos, 10) + _codificar(secrets.randbits(80), 16)


def es_ulid(valor) -> bool:
    return isinstance(valor, str) and bool(_PATRON.match(valor))


def ulid_minimo(milisegundos: int) -> str:
    """Menor ULID posible para un instante: sirve como límite inferior en consultas por rango."""
    return _codificar(milisegundos, 10) + "0" * 16
