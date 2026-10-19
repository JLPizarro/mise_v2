"""Función `impresion`: atiende a las impresoras de cocina y caja con el protocolo CloudPRNT.

URL que se configura en la impresora:  https://<api>/impresion/<tenant_id>/<local_id>/<impresora_id>
Autenticación: HTTP Basic, usuario = impresora_id, contraseña = clave de la impresora (se obtiene al
crearla o rotarla en administración). Sin autorizador JWT: la valida esta función, comparando el
hash en tiempo constante.

  POST   la impresora informa su estado y pregunta si hay trabajo  -> {"jobReady": ...}
  GET    descarga el trabajo (?token=<trabajo_id>)                  -> text/plain
  DELETE confirma (?token=...&code=200%20OK)                        -> el trabajo pasa a HECHO

Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, IMPRESION_ASCII (opcional, "true" quita acentos),
           LOG_LEVEL (opcional)
"""

import base64
import binascii
import logging
import os
import time

from pos_dominio import autorizacion, claves, impresion, tiempo
from pos_dominio.cambios import Borrar, Crear, existe
from pos_dominio.contexto import Contexto
from pos_dominio.errores import ErrorDominio, NoAutenticado, NoEncontrado
from pos_dominio.infra import aws, http
from pos_dominio.infra.logs import correlacion
from pos_dominio.modelos import Impresora

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION")
app = http.Aplicacion("impresion")
log = logging.getLogger("pos.impresion")
OP, CFG = claves.TABLA_OPERACION, claves.TABLA_CONFIGURACION
TTL_HECHO = 7 * 24 * 3600
_CACHE_SEGUNDOS = 60
_cache: dict[tuple, tuple[float, Impresora]] = {}
RUTA = "/impresion/{tenant_id}/{local_id}/{impresora_id}"


def _autenticar(peticion) -> tuple[str, Impresora]:
    tenant_id = claves.validar_id(peticion.parametros.get("tenant_id"), "tenant_id")
    local_id = claves.validar_id(peticion.parametros.get("local_id"), "local_id")
    impresora_id = claves.validar_id(peticion.parametros.get("impresora_id"), "impresora_id")
    correlacion(tenant_id=tenant_id, local_id=local_id, impresora_id=impresora_id)
    encabezado = peticion.encabezados.get("authorization", "")
    if not encabezado.lower().startswith("basic "):
        raise NoAutenticado("Credenciales de impresora requeridas", codigo="IMPRESORA_SIN_CREDENCIALES")
    try:
        usuario, _, clave = base64.b64decode(encabezado[6:]).decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise NoAutenticado("Credenciales de impresora inválidas", codigo="IMPRESORA_NO_AUTORIZADA") from error

    L = claves.local(tenant_id, local_id)
    clave_cache = (L, impresora_id)
    guardada = _cache.get(clave_cache)
    if guardada and guardada[0] > time.monotonic():
        impresora = guardada[1]
    else:
        datos = aws.almacen().obtener(CFG, L, claves.sk_impresora(impresora_id), consistente=False)
        impresora = Impresora.desde_atributos(datos) if datos else None
        if impresora is not None:
            _cache[clave_cache] = (time.monotonic() + _CACHE_SEGUNDOS, impresora)
    valida = impresora is not None and usuario == impresora_id and impresora.activa and \
        autorizacion.verificar_clave_impresora(clave, impresora.clave_hash, impresora.clave_sal)
    if not valida:
        raise NoAutenticado("Credenciales de impresora inválidas", codigo="IMPRESORA_NO_AUTORIZADA")
    return L, impresora


def _siguiente(L: str, impresora_id: str) -> dict | None:
    filas = aws.almacen().consultar(OP, claves.impresora(L, impresora_id), prefijo="PEND#", limite=1)
    return filas[0] if filas else None


@app.ruta(f"POST {RUTA}", publica=True)
def consultar(peticion):
    L, impresora = _autenticar(peticion)
    return 200, impresion.respuesta_consulta(_siguiente(L, impresora.impresora_id))


@app.ruta(f"GET {RUTA}", publica=True)
def descargar(peticion):
    L, impresora = _autenticar(peticion)
    token = peticion.query.get("token")
    if token:
        trabajo = aws.almacen().obtener(OP, claves.impresora(L, impresora.impresora_id),
                                        claves.sk_trabajo_pendiente(claves.validar_id(token, "token")))
    else:
        trabajo = _siguiente(L, impresora.impresora_id)
    if trabajo is None:
        raise NoEncontrado("No hay trabajo pendiente", codigo="SIN_TRABAJO")
    solo_ascii = os.environ.get("IMPRESION_ASCII", "").lower() == "true"
    return http.respuesta_texto(200, impresion.contenido(trabajo, solo_ascii=solo_ascii))


@app.ruta(f"DELETE {RUTA}", publica=True)
def confirmar(peticion):
    L, impresora = _autenticar(peticion)
    token = claves.validar_id(peticion.query.get("token", ""), "token")
    codigo = peticion.query.get("code", "")
    almacen = aws.almacen()
    pk = claves.impresora(L, impresora.impresora_id)
    trabajo = almacen.obtener(OP, pk, claves.sk_trabajo_pendiente(token))
    if trabajo is None:
        # Confirmación repetida: el trabajo ya se movió a HECHO. Idempotente.
        return 200, {"confirmado": True}
    ahora = tiempo.ahora_utc()
    intentos = int(trabajo.get("intentos_fallidos", 0)) + (0 if impresion.impreso_ok(codigo) else 1)
    if not impresion.impreso_ok(codigo) and intentos < impresion.MAX_INTENTOS_FALLIDOS:
        log.warning("la impresora informó un error", extra={"trabajo_id": token, "code": codigo})
        almacen.actualizar(OP, pk, claves.sk_trabajo_pendiente(token),
                           asignar={"intentos_fallidos": intentos, "ultimo_error": codigo[:100]},
                           condicion=existe())
        return 200, {"confirmado": False, "reintentara": True}

    hecho = {k: v for k, v in trabajo.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}
    hecho.update({"estado": "impreso" if impresion.impreso_ok(codigo) else "error", "codigo_impresora": codigo[:100],
                  "impreso_en": tiempo.iso(ahora), "expira_en": tiempo.epoch(ahora) + TTL_HECHO})
    ctx = Contexto(tenant_id=L.split("#")[1], local_id=L.split("#")[3], usuario_id=f"impresora:{impresora.impresora_id}",
                   rol="sistema", command_id="", ahora=ahora)
    try:
        almacen.aplicar_sistema(ctx, [
            Borrar(tabla=OP, pk=pk, sk=claves.sk_trabajo_pendiente(token), condicion=existe()),
            Crear(tabla=OP, pk=pk, sk=claves.sk_trabajo_hecho(token), atributos=hecho),
        ], [])
    except ErrorDominio:
        return 200, {"confirmado": True}  # otra confirmación ganó la carrera
    return 200, {"confirmado": True, "estado": hecho["estado"]}


lambda_handler = app
