"""Identidad y autorización de cada petición.

1. El autorizador JWT del API Gateway ya validó firma, emisor, audiencia y vigencia del ID token de
   Google. Aquí se leen los claims de requestContext.authorizer.jwt.claims.
2. Se exige email_verified = true.
3. Se busca USER#<sub> en `configuracion`: perfil y una membresía por local (cliente, rol, estado).
   Si la persona entra por primera vez, sus invitaciones (por email) se convierten en membresías.
4. Personas inexistentes, archivadas o sin membresía activa en el local pedido: 403, aunque el
   token sea válido.

El rol y el cliente salen siempre de `configuracion`; el local de la ruta solo elige cuál
membresía usar. Se guarda en memoria de la función hasta 60 s.
"""

import time
from dataclasses import dataclass, field

from pos_dominio import tiempo
from pos_dominio.contexto import Contexto
from pos_dominio.errores import Conflicto, NoAutenticado, Prohibido
from pos_dominio.modelos import Membresia

CACHE_SEGUNDOS = 60
_CACHE: dict[str, tuple[float, "Sesion"]] = {}


@dataclass
class Sesion:
    sub: str
    email: str
    nombre: str
    membresias: list = field(default_factory=list)

    def membresia(self, local_id: str) -> Membresia:
        candidatas = [m for m in self.membresias if m.local_id == local_id]
        if len(candidatas) > 1:
            raise Conflicto("El local existe en más de un cliente; contacta al soporte", codigo="LOCAL_AMBIGUO")
        if not candidatas or not candidatas[0].activa:
            raise Prohibido("No tienes acceso a este local", codigo="SIN_ACCESO_AL_LOCAL")
        return candidatas[0]

    def contexto(self, local_id: str, *, command_id: str = "", request_id: str = "", origen: str = "normal",
                 ahora=None) -> Contexto:
        membresia = self.membresia(local_id)
        return Contexto(tenant_id=membresia.tenant_id, local_id=membresia.local_id, usuario_id=self.sub,
                        rol=membresia.rol, command_id=command_id, usuario_nombre=membresia.nombre or self.nombre,
                        origen=origen, request_id=request_id, ahora=ahora or tiempo.ahora_utc())


def _verdadero(valor) -> bool:
    # En HTTP API los claims llegan como texto: "true".
    return valor is True or str(valor).lower() == "true"


def limpiar_cache() -> None:
    _CACHE.clear()


def sesion_desde_claims(claims: dict, almacen, *, reloj=time.monotonic) -> Sesion:
    sub = claims.get("sub")
    if not sub:
        raise NoAutenticado("Falta la identidad del usuario", codigo="SIN_IDENTIDAD")
    if not _verdadero(claims.get("email_verified")):
        raise Prohibido("El email de la cuenta de Google no está verificado", codigo="EMAIL_NO_VERIFICADO")
    return sesion_de(sub, claims.get("email", ""), claims.get("name", ""), almacen, reloj=reloj)


def sesion_de(sub: str, email: str, nombre: str, almacen, *, reloj=time.monotonic) -> Sesion:
    ahora = reloj()
    guardada = _CACHE.get(sub)
    if guardada and guardada[0] > ahora:
        return guardada[1]

    perfil, membresias = almacen.identidad(sub)
    if perfil is None:
        if email:
            perfil, membresias = almacen.vincular_invitaciones(sub, email.strip().lower(), nombre)
        if perfil is None:
            raise Prohibido("Esta cuenta de Google no está autorizada. Pide que un administrador te agregue.",
                            codigo="USUARIO_NO_REGISTRADO")
    if perfil.get("estado") == "archivado":
        raise Prohibido("Tu cuenta está deshabilitada", codigo="USUARIO_ARCHIVADO")

    sesion = Sesion(sub=sub, email=perfil.get("email", email), nombre=perfil.get("nombre", nombre),
                    membresias=membresias)
    _CACHE[sub] = (ahora + CACHE_SEGUNDOS, sesion)
    return sesion
