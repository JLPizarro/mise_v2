"""Definición común de una operación de negocio."""

from collections.abc import Callable
from dataclasses import dataclass

from pos_dominio.cambios import Reemplazar


@dataclass(frozen=True)
class Operacion:
    nombre: str          # se guarda en el CMD y forma parte del hash del cuerpo
    accion: str          # acción de la matriz de roles (pos_dominio.roles)
    leer: Callable       # (almacen, ctx, cuerpo) -> estado
    decidir: Callable    # (estado, ctx, cuerpo) -> Resultado | Rechazo   (puro)


def reemplazar(tabla: str, pk: str, sk: str, atributos: dict) -> Reemplazar:
    return Reemplazar(tabla=tabla, pk=pk, sk=sk, atributos=atributos)
