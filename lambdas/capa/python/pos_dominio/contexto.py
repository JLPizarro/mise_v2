"""Contexto de una operación: quién la pide, en qué local, con qué comando y a qué hora.

El cliente, el local y el rol salen siempre de la membresía guardada en `configuracion`, nunca del
token ni del cuerpo de la petición. Este objeto lo arma la capa HTTP después de autorizar.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from pos_dominio import claves, ids, tiempo

ORIGENES = ("normal", "contingencia", "cola_local")


@dataclass
class Contexto:
    tenant_id: str
    local_id: str
    usuario_id: str
    rol: str
    command_id: str
    usuario_nombre: str = ""
    origen: str = "normal"
    request_id: str = ""
    # Hora de negocio. En contingencia es la hora en que el usuario hizo la acción, no la del drenado.
    ahora: datetime = field(default_factory=tiempo.ahora_utc)
    nuevo_id: Callable[[], str] = ids.nuevo_ulid

    @property
    def L(self) -> str:
        return claves.local(self.tenant_id, self.local_id)

    @property
    def ahora_iso(self) -> str:
        return tiempo.iso(self.ahora)
