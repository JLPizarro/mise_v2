"""Función `reservas`: reservas públicas. ESQUELETO, sin reglas de negocio todavía.

El POS local no tenía reservas implementadas (solo una tabla sin rutas). Por decisión del equipo
(punto de control 1, P3) primero se migra lo que existe; las reglas de reserva (duración,
anticipación, capacidad, horario) están pendientes de definir (pregunta P12).

Lo que sí queda resuelto y probado:
- El cliente y el local se resuelven por la ruta, nunca por el cuerpo.
- La ruta no tiene autorizador; el API Gateway le aplica el límite de tasa más estricto.
- El local debe existir; si no, 404 (sin revelar otros datos).

Manejador: lambda_function.lambda_handler
Variables: TABLA_CONFIGURACION, TABLA_OPERACION, LOG_LEVEL (opcional)
"""

from pos_dominio import claves
from pos_dominio.errores import ErrorDominio, NoEncontrado
from pos_dominio.infra import aws, http

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION")
app = http.Aplicacion("reservas")


class NoImplementado(ErrorDominio):
    http = 501
    codigo = "NO_IMPLEMENTADO"


def _local(peticion):
    L = claves.local(peticion.parametros.get("tenant_id"), peticion.parametros.get("local_id"))
    local = aws.almacen().config_local(L)
    if local is None:
        raise NoEncontrado("Local no encontrado", codigo="LOCAL_NO_ENCONTRADO")
    return local


@app.ruta("GET /publico/{tenant_id}/{local_id}/reservas/disponibilidad", publica=True)
def disponibilidad(peticion):
    _local(peticion)
    raise NoImplementado("Las reservas en línea aún no están disponibles para este local")


@app.ruta("POST /publico/{tenant_id}/{local_id}/reservas", publica=True)
def reservar(peticion):
    _local(peticion)
    raise NoImplementado("Las reservas en línea aún no están disponibles para este local")


lambda_handler = app
