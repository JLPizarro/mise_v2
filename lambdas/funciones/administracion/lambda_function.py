"""Función `administracion`: catálogo, salón, cuartos, impresoras, inventario, configuración del local,
personal y estaciones de caja.

Para no crear cuarenta rutas a mano en la consola, el recurso va en la ruta:
  GET    /locales/{local_id}/admin/{recurso}                 listar
  POST   /locales/{local_id}/admin/{recurso}                 crear
  PATCH  /locales/{local_id}/admin/{recurso}/{id}            editar
  DELETE /locales/{local_id}/admin/{recurso}/{id}            eliminar (invitaciones, estaciones)
  POST   /locales/{local_id}/admin/{recurso}/{id}/{accion}   acción (impresoras/{id}/rotar-clave)
Son rutas explícitas con parámetros, no un comodín: las peticiones OPTIONS del navegador no llegan
aquí y CORS lo resuelve el API Gateway.

Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, LOG_LEVEL (opcional)
"""

from pos_dominio import claves, roles
from pos_dominio.errores import NoEncontrado
from pos_dominio.infra import api, aws, http
from pos_dominio.operaciones import administracion as A

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION")
app = http.Aplicacion("administracion")
CFG = claves.TABLA_CONFIGURACION
_ACCIONES = {"rotar-clave"}


def _operacion(recurso: str, verbo: str):
    operacion = A.OPERACIONES.get((recurso, verbo))
    if operacion is None:
        raise http.RutaNoEncontrada(f"No existe '{verbo}' para '{recurso}'")
    return operacion


def _cuerpo(peticion, recurso: str) -> dict:
    cuerpo = dict(peticion.json())
    identificador = peticion.parametros.get("id")
    campo = A.CAMPO_ID.get(recurso)
    # La configuración del local no tiene ID propio: PATCH .../admin/configuracion/local
    if identificador is not None and campo is not None:
        cuerpo[campo] = identificador
    return cuerpo


@app.ruta("GET /locales/{local_id}/admin/{recurso}")
def listar(peticion):
    recurso = peticion.parametros["recurso"]
    almacen = aws.almacen()
    if recurso == "personal":
        ctx = api.contexto(peticion, accion="admin.personal")
        filas = almacen.personal(ctx.L)
        return 200, {"personal": [{"sub": f.get("sub"), "nombre": f.get("nombre"), "email": f.get("email"),
                                   "rol": f.get("rol"), "estado": f.get("estado"),
                                   "invitacion": f.get("tipo_item") == "INVITACION"} for f in filas]}
    ctx = api.contexto(peticion, accion="admin.estructura")
    if recurso == "configuracion":
        local = almacen.obtener(CFG, ctx.L, claves.SK_LOCAL, consistente=True)
        if local is None:
            raise NoEncontrado("Configuración del local no encontrada", codigo="LOCAL_NO_ENCONTRADO")
        return 200, A.vista_local(local)
    prefijo = A.LISTADOS.get(recurso)
    if prefijo is None:
        raise http.RutaNoEncontrada(f"Recurso desconocido: {recurso}")
    return 200, {recurso: [A.limpiar(f) for f in almacen.listar(CFG, ctx.L, prefijo, consistente=True)]}


@app.ruta("POST /locales/{local_id}/admin/{recurso}", escritura=True)
def crear(peticion):
    recurso = peticion.parametros["recurso"]
    return api.ejecutar_http(peticion, _operacion(recurso, "crear"), _cuerpo(peticion, recurso))


@app.ruta("PATCH /locales/{local_id}/admin/{recurso}/{id}", escritura=True)
def editar(peticion):
    recurso = peticion.parametros["recurso"]
    return api.ejecutar_http(peticion, _operacion(recurso, "editar"), _cuerpo(peticion, recurso))


@app.ruta("DELETE /locales/{local_id}/admin/{recurso}/{id}", escritura=True)
def eliminar(peticion):
    recurso = peticion.parametros["recurso"]
    return api.ejecutar_http(peticion, _operacion(recurso, "eliminar"), _cuerpo(peticion, recurso))


@app.ruta("POST /locales/{local_id}/admin/{recurso}/{id}/{accion}", escritura=True)
def accion(peticion):
    recurso, nombre = peticion.parametros["recurso"], peticion.parametros["accion"]
    if nombre not in _ACCIONES:
        raise http.RutaNoEncontrada(f"Acción desconocida: {nombre}")
    return api.ejecutar_http(peticion, _operacion(recurso, nombre), _cuerpo(peticion, recurso))


assert all(roles.MATRIZ.get(op.accion) for op in A.OPERACIONES.values()), "acción sin roles"
lambda_handler = app
