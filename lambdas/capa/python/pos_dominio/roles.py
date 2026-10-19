"""Matriz de rol por acción. Se aplica en el servidor en cada operación: el dominio no confía en
que la interfaz haya ocultado un botón.

Diferencias con el local (documentadas en docs/migracion/caracterizacion.md):
- `cocina` ya no puede escribir comandas ni cambiar mesas (antes cualquier rol podía; no tiene
  pantalla).
- bloquear mesas y asignar garzón pasa a dueño, admin y cajero (D4: antes cualquier rol).
- solo un dueño gestiona membresías de dueño (D16).
"""

from pos_dominio.errores import Prohibido

_SALON = {"dueno", "admin", "cajero", "garzon"}
_CAJA = {"dueno", "admin", "cajero"}
_ADMIN = {"dueno", "admin"}

MATRIZ: dict[str, set[str]] = {
    "salon.ver": _SALON,
    "pedido.escribir": _SALON,
    "mesa.gestionar": _CAJA,
    "caja.cobrar": _CAJA,
    "caja.turno": _CAJA,
    "caja.retiro": _CAJA,
    "caja.contingencia": _CAJA,
    "admin.estructura": _ADMIN,
    "admin.personal": _ADMIN,
    "admin.dueno": {"dueno"},
    "reportes.ver": _ADMIN,
    "mensajeria.administrar": _ADMIN,
    "autorizar": _ADMIN,
}


def permitido(rol: str, accion: str) -> bool:
    return rol in MATRIZ.get(accion, set())


def exigir(rol: str, accion: str) -> None:
    if not permitido(rol, accion):
        raise Prohibido("No tienes permisos para esta acción", codigo="ROL_NO_PERMITIDO",
                        detalle={"accion": accion})
