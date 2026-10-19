"""Código de autorización presencial (retiros de caja) y claves de impresora.

- Hash con hashlib.pbkdf2_hmac SHA-256, sal aleatoria de 16 bytes por usuario y las iteraciones
  guardadas junto al hash, para poder subirlas sin invalidar los códigos existentes.
- Comparación en tiempo constante con hmac.compare_digest.
- Bloqueo: 5 intentos fallidos dentro de 15 minutos bloquean al autorizador por 15 minutos.

Compatible con el formato del local (`sal_hex$hash_hex`, 200.000 iteraciones), ver
`desde_formato_local`.
"""

import hashlib
import hmac
import os
import re
import secrets

from pos_dominio.errores import Prohibido, Validacion
from pos_dominio.modelos import Bloqueo

ITERACIONES = 200_000
MAX_INTENTOS = 5
VENTANA_SEGUNDOS = 15 * 60
_FORMATO_CODIGO = re.compile(r"^\d{4,8}$")


def validar_formato_codigo(codigo) -> str:
    """4 a 8 dígitos, igual que POST /api/usuarios/me/pin del local."""
    if not isinstance(codigo, str) or not _FORMATO_CODIGO.match(codigo.strip()):
        raise Validacion("El código debe tener entre 4 y 8 dígitos", codigo="CODIGO_FORMATO")
    return codigo.strip()


def hashear(secreto: str, *, iteraciones: int = ITERACIONES, sal: bytes | None = None) -> tuple[str, str, int]:
    sal = sal if sal is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", secreto.encode("utf-8"), sal, iteraciones)
    return digest.hex(), sal.hex(), iteraciones


def verificar(secreto: str, hash_hex: str | None, sal_hex: str | None, iteraciones: int | None) -> bool:
    if not (hash_hex and sal_hex and iteraciones) or not isinstance(secreto, str):
        return False
    try:
        sal = bytes.fromhex(sal_hex)
        esperado = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    candidato = hashlib.pbkdf2_hmac("sha256", secreto.encode("utf-8"), sal, int(iteraciones))
    return hmac.compare_digest(candidato, esperado)


def desde_formato_local(guardado: str) -> tuple[str, str, int]:
    """Convierte `sal_hex$hash_hex` del POS local a (hash, sal, iteraciones)."""
    sal_hex, hash_hex = guardado.split("$", 1)
    return hash_hex, sal_hex, ITERACIONES


def nueva_clave_impresora() -> str:
    """Clave aleatoria para una impresora. Se muestra una sola vez; se guarda solo su hash."""
    return secrets.token_urlsafe(24)


# --- Bloqueo por intentos fallidos ---------------------------------------------------------------


def verificar_no_bloqueado(bloqueo: Bloqueo | None, ahora: int) -> None:
    # TTL de DynamoDB puede tardar hasta 48 h en borrar el ítem: siempre se compara con la hora.
    if bloqueo and bloqueo.bloqueado_hasta > ahora:
        minutos = max(1, (bloqueo.bloqueado_hasta - ahora + 59) // 60)
        raise Prohibido(f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} minutos.",
                        codigo="AUTORIZACION_BLOQUEADA", detalle={"minutos": minutos})


def registrar_fallo(bloqueo: Bloqueo | None, ahora: int) -> Bloqueo:
    """Devuelve el estado del contador después de un intento fallido."""
    if bloqueo is None or bloqueo.ventana_hasta <= ahora:
        nuevo = Bloqueo(intentos=1, ventana_hasta=ahora + VENTANA_SEGUNDOS, bloqueado_hasta=0,
                        version=bloqueo.version if bloqueo else 0)
    else:
        nuevo = Bloqueo(intentos=bloqueo.intentos + 1, ventana_hasta=bloqueo.ventana_hasta,
                        bloqueado_hasta=bloqueo.bloqueado_hasta, version=bloqueo.version)
    if nuevo.intentos >= MAX_INTENTOS:
        nuevo.bloqueado_hasta = ahora + VENTANA_SEGUNDOS
    return nuevo


def intentos_restantes(bloqueo: Bloqueo) -> int:
    return max(MAX_INTENTOS - bloqueo.intentos, 0)


# --- claves de impresora -----------------------------------------------------------------------------

def hashear_clave_impresora(clave: str, sal: bytes | None = None) -> tuple[str, str]:
    """La clave de impresora es aleatoria de 192 bits, no un código elegido por una persona: no se
    puede adivinar por fuerza bruta, así que basta SHA-256 con sal. PBKDF2 aquí costaría cientos
    de milisegundos de CPU en cada consulta de la impresora (cada pocos segundos)."""
    sal = sal if sal is not None else os.urandom(16)
    return hashlib.sha256(sal + clave.encode("utf-8")).hexdigest(), sal.hex()


def verificar_clave_impresora(clave: str, hash_hex: str | None, sal_hex: str | None) -> bool:
    if not (hash_hex and sal_hex and isinstance(clave, str)):
        return False
    try:
        candidato, _ = hashear_clave_impresora(clave, bytes.fromhex(sal_hex))
    except ValueError:
        return False
    return hmac.compare_digest(candidato, hash_hex)
