"""Errores de dominio. La capa de infraestructura (routers) los traduce a códigos HTTP."""


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class UnauthorizedError(DomainError):
    pass
