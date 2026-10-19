"""Validación explícita de cuerpos JSON, en reemplazo de los modelos de Pydantic.

Cada función lee un campo de un dict, valida tipo y rango, y lanza Validacion con el nombre del
campo en `detalle`. Los booleanos nunca pasan como enteros (en Python, True es un int).
"""

from decimal import Decimal, InvalidOperation

from pos_dominio import ids
from pos_dominio.claves import validar_id
from pos_dominio.errores import Validacion

_FALTA = object()


def _error(campo: str, mensaje: str) -> Validacion:
    return Validacion(f"{campo}: {mensaje}", codigo="CAMPO_INVALIDO", detalle={"campo": campo})


def objeto(valor, campo: str = "cuerpo") -> dict:
    if not isinstance(valor, dict):
        raise _error(campo, "debe ser un objeto JSON")
    return valor


def entero(datos: dict, campo: str, *, requerido: bool = True, defecto=None, minimo: int | None = None,
           maximo: int | None = None):
    valor = datos.get(campo, _FALTA)
    if valor is _FALTA or valor is None:
        if requerido:
            raise _error(campo, "es obligatorio")
        return defecto
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise _error(campo, "debe ser un número entero")
    if minimo is not None and valor < minimo:
        raise _error(campo, f"debe ser mayor o igual a {minimo}")
    if maximo is not None and valor > maximo:
        raise _error(campo, f"debe ser menor o igual a {maximo}")
    return valor


def texto(datos: dict, campo: str, *, requerido: bool = True, defecto=None, max_largo: int = 200,
          vacio: bool = False):
    valor = datos.get(campo, _FALTA)
    if valor is _FALTA or valor is None:
        if requerido:
            raise _error(campo, "es obligatorio")
        return defecto
    if not isinstance(valor, str):
        raise _error(campo, "debe ser texto")
    valor = valor.strip()
    if not valor and not vacio:
        if requerido:
            raise _error(campo, "no puede estar vacío")
        return defecto
    if len(valor) > max_largo:
        raise _error(campo, f"admite hasta {max_largo} caracteres")
    return valor


def uno_de(datos: dict, campo: str, opciones, *, requerido: bool = True, defecto=None):
    valor = datos.get(campo, _FALTA)
    if valor is _FALTA or valor is None:
        if requerido:
            raise _error(campo, "es obligatorio")
        return defecto
    if valor not in opciones:
        raise _error(campo, f"debe ser uno de: {', '.join(sorted(opciones))}")
    return valor


def booleano(datos: dict, campo: str, *, requerido: bool = False, defecto: bool = False) -> bool:
    valor = datos.get(campo, _FALTA)
    if valor is _FALTA or valor is None:
        if requerido:
            raise _error(campo, "es obligatorio")
        return defecto
    if not isinstance(valor, bool):
        raise _error(campo, "debe ser true o false")
    return valor


def lista(datos: dict, campo: str, *, requerido: bool = True, minimo: int = 0, maximo: int = 100) -> list:
    valor = datos.get(campo, _FALTA)
    if valor is _FALTA or valor is None:
        if requerido:
            raise _error(campo, "es obligatorio")
        return []
    if not isinstance(valor, list):
        raise _error(campo, "debe ser una lista")
    if not minimo <= len(valor) <= maximo:
        raise _error(campo, f"debe tener entre {minimo} y {maximo} elementos")
    return valor


def identificador(datos: dict, campo: str, *, requerido: bool = True):
    valor = texto(datos, campo, requerido=requerido, max_largo=64)
    if valor is None:
        return None
    return validar_id(valor, campo)


def command_id(valor) -> str:
    if not ids.es_ulid(valor):
        raise Validacion("El encabezado X-Command-Id debe ser un ULID", codigo="COMMAND_ID_INVALIDO")
    return valor


def milesimas(datos: dict, campo: str, *, requerido: bool = True, defecto=None, maximo: int = 1_000_000_000):
    """Cantidad decimal con hasta 3 decimales (kg, l...) guardada como entero en milésimas.

    Igual de exacta que el NUMERIC(12,3) del local, sin usar float."""
    valor = datos.get(campo, _FALTA)
    if valor is _FALTA or valor is None:
        if requerido:
            raise _error(campo, "es obligatorio")
        return defecto
    if isinstance(valor, bool) or not isinstance(valor, (int, Decimal, str)):
        raise _error(campo, "debe ser un número")
    try:
        numero = Decimal(str(valor))
    except InvalidOperation as error:
        raise _error(campo, "debe ser un número") from error
    if not numero.is_finite() or numero < 0:
        raise _error(campo, "debe ser un número mayor o igual a 0")
    escalado = numero * 1000
    if escalado != escalado.to_integral_value():
        raise _error(campo, "admite hasta 3 decimales")
    resultado = int(escalado)
    if resultado > maximo:
        raise _error(campo, "es demasiado grande")
    return resultado
