"""Errores del dominio. Cada uno sabe su código estable y su estado HTTP.

Regla de la plataforma: un rechazo de negocio es siempre 4xx distinto de 429. La PWA pasa a
contingencia solo ante 5xx, 429 o tiempo agotado, así que ningún error de este módulo puede usar
429 (por eso el bloqueo de autorización es 403 y no 429).
"""


class ErrorDominio(Exception):
    http = 422
    codigo = "VALIDACION"
    # True si el error depende de una carrera con otra escritura: no se guarda como respuesta
    # definitiva del comando, porque reintentarlo puede tener éxito.
    transitorio = False

    def __init__(self, mensaje: str, *, codigo: str | None = None, detalle: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        if codigo:
            self.codigo = codigo
        self.detalle = detalle or {}

    def cuerpo(self) -> dict:
        cuerpo = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.detalle:
            cuerpo["detalle"] = self.detalle
        return cuerpo


class Validacion(ErrorDominio):
    http = 422
    codigo = "VALIDACION"


class NoEncontrado(ErrorDominio):
    http = 404
    codigo = "NO_ENCONTRADO"


class Conflicto(ErrorDominio):
    http = 409
    codigo = "CONFLICTO"


class ConflictoConcurrencia(Conflicto):
    codigo = "CONFLICTO_CONCURRENCIA"
    transitorio = True


class Prohibido(ErrorDominio):
    http = 403
    codigo = "PROHIBIDO"


class NoAutenticado(ErrorDominio):
    http = 401
    codigo = "NO_AUTENTICADO"


class ErrorInfraestructura(Exception):
    """Falla de AWS (limitación, error interno, red, permisos). Activa la contingencia en pedidos."""

    def __init__(self, mensaje: str, *, causa: str = ""):
        super().__init__(mensaje)
        self.causa = causa


class ErrorDeCodigo(Exception):
    """Defecto del propio código (por ejemplo, un ítem que DynamoDB rechaza por formato).

    Se responde 500 y se alerta. No se manda a contingencia: reaplicarlo fallaría igual (M15)."""


class Reintentar(Exception):
    """Señal interna: una condición de versión falló; el ejecutor relee y decide otra vez."""

    def __init__(self, error: ErrorDominio | None = None):
        super().__init__("reintentar")
        self.error = error


class ComandoDuplicado(Exception):
    """Señal interna: el ítem CMD ya existía; se devuelve la respuesta guardada."""
