"""Función `mensajeria`: administración de los recursos de mensajería del local (dueño y admin).

Rutas (prefijo /locales/{local_id}/mensajeria):
  GET    /canales                               catálogo de canales, rutas y avisos, con el estado de cada cola
  GET    /destinos                              destinos del local con sus reglas y el estado de su suscripción
  POST   /destinos                              crear destino {nombre, tipo: correo|cola, correo?, avisos: [...]}
  DELETE /destinos/{destino_id}                 eliminar destino (suscripción y, si es cola, la cola)
  POST   /destinos/{destino_id}/reglas          crear regla {aviso}
  DELETE /destinos/{destino_id}/reglas/{aviso}  eliminar regla
  GET    /destinos/{destino_id}/mensajes        ver lo que llegó a un destino de tipo cola (sin consumirlo)
  POST   /pruebas                               publicar un aviso de prueba {aviso}: muestra quién debe recibirlo
  GET    /fallidos                              mensajes apartados en las colas de fallidos, con su diagnóstico
  POST   /fallidos/{mensaje_id}/reprocesar      {canal}: devolverlo a su cola de origen
  POST   /fallidos/{mensaje_id}/descartar       {canal}: borrarlo de la cola de fallidos

Responsabilidades: el catálogo y la validación están en `pos_dominio.mensajeria`; las operaciones de
AWS, en `pos_dominio.infra.mensajeria_aws.GestorMensajeria`. Aquí solo se orquesta: permisos,
idempotencia por X-Command-Id y el registro en DynamoDB (destino + evento de auditoría en una
transacción). Los canales del sistema no se pueden crear ni borrar desde aquí: los gestiona el
despliegue a partir del mismo catálogo.

Manejador: lambda_function.lambda_handler
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, TEMA_DUENO_ARN, LOG_LEVEL (opcional)
"""

import json
import os

from pos_dominio import claves, mensajeria as M
from pos_dominio.cambios import Borrar, Crear, Evento, Guardar
from pos_dominio.ejecutor import hash_cuerpo
from pos_dominio.errores import ComandoDuplicado, Conflicto, NoEncontrado, Validacion
from pos_dominio.infra import api, aws, http
from pos_dominio.infra.mensajeria_aws import GestorMensajeria

aws.exigir_entorno("TABLA_OPERACION", "TABLA_CONFIGURACION", "TEMA_DUENO_ARN")
app = http.Aplicacion("mensajeria")
CFG, OP = claves.TABLA_CONFIGURACION, claves.TABLA_OPERACION
BASE = "/locales/{local_id}/mensajeria"


def _ctx(peticion):
    return api.contexto(peticion, accion="mensajeria.administrar")


def _gestor() -> GestorMensajeria:
    return GestorMensajeria(os.environ["TEMA_DUENO_ARN"], espera_lectura=int(os.environ.get("ESPERA_SQS_SEGUNDOS", "1")))


def _comando(peticion, ctx, nombre: str, cuerpo: dict, accion, deshacer=None):
    """Idempotencia por X-Command-Id: el mismo comando devuelve la misma respuesta sin repetir efectos.

    `accion()` hace los cambios en AWS (repetibles) y devuelve (http, respuesta, cambios, eventos); los
    cambios de DynamoDB y el CMD se guardan juntos. Si esa transacción falla, `deshacer()` revierte lo
    hecho en AWS (por ejemplo, cuando dos personas crean a la vez un destino con el mismo nombre)."""
    almacen = aws.almacen()
    huella = hash_cuerpo(nombre, cuerpo)
    previo = almacen.leer_comando(ctx.L, ctx.command_id)
    if previo is None:
        estado, respuesta, cambios, eventos = accion()
        try:
            almacen.aplicar(ctx, nombre, huella, http=estado, respuesta=respuesta, estado_cmd="aplicado",
                            cambios=cambios, eventos=eventos)
            return http.respuesta(estado, respuesta)
        except ComandoDuplicado:
            previo = almacen.leer_comando(ctx.L, ctx.command_id)
        except Exception:
            if deshacer:
                deshacer()
            raise
    if previo.get("hash_cuerpo") != huella:
        raise Validacion("El X-Command-Id ya se usó para otra operación", codigo="COMANDO_REUTILIZADO")
    return http.respuesta(int(previo["http_status"]), json.loads(previo["respuesta"]),
                          encabezados={"x-comando-repetido": "true"})


def _destinos(ctx) -> list[dict]:
    return aws.almacen().listar(CFG, ctx.L, "DESTINO#", consistente=True)


def _destino(ctx, destino_id: str) -> dict:
    item = aws.almacen().obtener(CFG, ctx.L, claves.sk_destino(M.validar_destino_id(destino_id)))
    if item is None:
        raise NoEncontrado("Destino no encontrado", codigo="DESTINO_NO_ENCONTRADO")
    return item


def _vista(item: dict, estado: str | None = None) -> dict:
    vista = {k: item.get(k) for k in ("destino_id", "nombre", "tipo", "correo", "avisos", "creado_en", "creado_por")}
    vista["cola"] = item.get("cola_nombre")
    vista["reglas"] = [{"aviso": a, "titulo": M.AVISOS[a].titulo} for a in item.get("avisos", []) if a in M.AVISOS]
    if estado is not None:
        vista["estado"] = estado
    return vista


def _politica(ctx, avisos: list[str]) -> dict:
    return M.politica_de_filtro(ctx.tenant_id, ctx.local_id, avisos)


# --- consulta -----------------------------------------------------------------------------------------

@app.ruta(f"GET {BASE}/canales")
def canales(peticion):
    _ctx(peticion)
    gestor = _gestor()
    lista = []
    for canal in M.CANALES.values():
        vista = {"id": canal.id, "tipo": canal.tipo, "nombre": canal.nombre_aws, "proposito": canal.proposito,
                 "productores": list(canal.productores), "consumidores": list(canal.consumidores),
                 "fifo": canal.fifo, "max_recepciones": canal.max_recepciones, "fallidos": canal.fallidos,
                 "tratamiento": canal.tratamiento, "protegido": True}
        if canal.tipo in ("cola", "cola_fallidos"):
            try:
                vista["estado"] = gestor.estado_cola(canal.nombre_aws) or {"no_existe": True}
            except Exception:  # noqa: BLE001 - el catálogo se muestra aunque una cola no responda
                vista["estado"] = None
        lista.append(vista)
    return 200, {
        "canales": lista,
        "rutas": [{"evento": r.evento, "canal": r.canal, "consumidor": r.consumidor, "efecto": r.efecto,
                   "condicion": r.condicion} for r in M.RUTAS],
        "avisos": [{"id": a.id, "titulo": a.titulo, "descripcion": a.descripcion, "canal": a.canal,
                    "administrable": a.administrable} for a in M.AVISOS.values()],
    }


@app.ruta(f"GET {BASE}/destinos")
def listar_destinos(peticion):
    ctx = _ctx(peticion)
    gestor = _gestor()
    vistas = []
    for item in _destinos(ctx):
        try:
            estado = gestor.estado_suscripcion(item["suscripcion_arn"])
        except Exception:  # noqa: BLE001
            estado = "desconocido"
        vistas.append(_vista(item, estado))
    return 200, {"destinos": sorted(vistas, key=lambda d: d["nombre"].lower()), "limite": M.MAX_DESTINOS_POR_LOCAL,
                 "avisos_disponibles": [{"id": a, "titulo": M.AVISOS[a].titulo} for a in M.AVISOS_ADMINISTRABLES]}


# --- destinos -------------------------------------------------------------------------------------------

@app.ruta(f"POST {BASE}/destinos", escritura=True)
def crear_destino(peticion):
    ctx = _ctx(peticion)
    cuerpo = peticion.json()
    gestor = _gestor()
    hecho: dict = {}

    def accion():
        datos = M.validar_destino(cuerpo)
        existentes = _destinos(ctx)
        if len(existentes) >= M.MAX_DESTINOS_POR_LOCAL:
            raise Conflicto(f"El local ya tiene {M.MAX_DESTINOS_POR_LOCAL} destinos; elimina uno antes de crear otro",
                            codigo="LIMITE_DE_DESTINOS")
        nombre_normal = M.normalizar_nombre(datos["nombre"])
        if any(M.normalizar_nombre(d["nombre"]) == nombre_normal for d in existentes):
            raise Conflicto("Ya existe un destino con ese nombre", codigo="DESTINO_DUPLICADO", detalle={"campo": "nombre"})
        if datos["tipo"] == "correo" and any(d.get("correo") == datos["correo"] for d in existentes):
            raise Conflicto("Ese correo ya es un destino de este local", codigo="CORREO_YA_REGISTRADO",
                            detalle={"campo": "correo"})

        destino_id = ctx.command_id  # mismo comando = mismos recursos en AWS (crear dos veces no duplica)
        politica = _politica(ctx, datos["avisos"])
        item = {"tipo_item": "DESTINO", "destino_id": destino_id, **datos, "creado_en": ctx.ahora_iso,
                "creado_por": ctx.usuario_id}
        if datos["tipo"] == "cola":
            nombre_cola = M.nombre_cola_destino(destino_id)
            url, arn = gestor.crear_cola_destino(nombre_cola)
            hecho["cola"] = nombre_cola
            item.update({"cola_nombre": nombre_cola, "cola_url": url, "cola_arn": arn})
            item["suscripcion_arn"] = gestor.suscribir("sqs", arn, politica)
        else:
            item["suscripcion_arn"] = gestor.suscribir("email", datos["correo"], politica)
        hecho["suscripcion"] = item["suscripcion_arn"]
        estado = gestor.estado_suscripcion(item["suscripcion_arn"])
        cambios = [
            # Guardar con versión 0 = crear con version 1: las reglas se editan después con control de versión.
            Guardar(tabla=CFG, pk=ctx.L, sk=claves.sk_destino(destino_id), atributos=item, version_leida=0,
                    reintentar=False, al_fallar=Conflicto("El destino ya existe", codigo="DESTINO_DUPLICADO")),
            Crear(tabla=CFG, pk=ctx.L, sk=f"UNICO#DESTINO#{nombre_normal}", atributos={"tipo_item": "UNICO", "ref_id": destino_id},
                  al_fallar=Conflicto("Ya existe un destino con ese nombre", codigo="DESTINO_DUPLICADO")),
        ]
        if datos["tipo"] == "correo":
            cambios.append(Crear(tabla=CFG, pk=ctx.L, sk=f"UNICO#DESTINO_CORREO#{datos['correo']}",
                                 atributos={"tipo_item": "UNICO", "ref_id": destino_id},
                                 al_fallar=Conflicto("Ese correo ya es un destino de este local", codigo="CORREO_YA_REGISTRADO")))
        evento = Evento("mensajeria.destino_creado", {"destino_id": destino_id, "nombre": datos["nombre"],
                                                      "tipo": datos["tipo"], "avisos": datos["avisos"]})
        return 201, _vista(item, estado), cambios, [evento]

    def deshacer():
        if "suscripcion" in hecho:
            gestor.desuscribir(hecho["suscripcion"])
        if "cola" in hecho:
            gestor.eliminar_cola(hecho["cola"])

    return _comando(peticion, ctx, "mensajeria.crear_destino", cuerpo, accion, deshacer)


@app.ruta(f"DELETE {BASE}/destinos/{{destino_id}}", escritura=True)
def eliminar_destino(peticion):
    ctx = _ctx(peticion)
    destino_id = peticion.parametros["destino_id"]
    gestor = _gestor()

    def accion():
        item = _destino(ctx, destino_id)
        gestor.desuscribir(item["suscripcion_arn"])
        if item.get("cola_nombre"):
            gestor.eliminar_cola(item["cola_nombre"])
        cambios = [Borrar(tabla=CFG, pk=ctx.L, sk=item["SK"]),
                   Borrar(tabla=CFG, pk=ctx.L, sk=f"UNICO#DESTINO#{M.normalizar_nombre(item['nombre'])}")]
        if item.get("correo"):
            cambios.append(Borrar(tabla=CFG, pk=ctx.L, sk=f"UNICO#DESTINO_CORREO#{item['correo']}"))
        evento = Evento("mensajeria.destino_eliminado", {"destino_id": item["destino_id"], "nombre": item["nombre"]})
        return 200, {"destino_id": item["destino_id"], "eliminado": True}, cambios, [evento]

    return _comando(peticion, ctx, "mensajeria.eliminar_destino", {"destino_id": destino_id}, accion)


# --- reglas ---------------------------------------------------------------------------------------------

def _guardar_avisos(ctx, item: dict, avisos: list[str]) -> Guardar:
    atributos = {k: v for k, v in item.items() if k not in ("PK", "SK", "version")}
    atributos["avisos"] = avisos
    return Guardar(tabla=CFG, pk=ctx.L, sk=item["SK"], atributos=atributos, version_leida=item.get("version", 1))


@app.ruta(f"POST {BASE}/destinos/{{destino_id}}/reglas", escritura=True)
def crear_regla(peticion):
    ctx = _ctx(peticion)
    destino_id = peticion.parametros["destino_id"]
    cuerpo = peticion.json()
    gestor = _gestor()

    def accion():
        desconocidos = sorted(set(cuerpo) - {"aviso"})
        if desconocidos:
            raise Validacion(f"Campo no permitido: {desconocidos[0]}", codigo="CAMPO_DESCONOCIDO",
                             detalle={"campo": desconocidos[0]})
        aviso = M.validar_aviso(cuerpo.get("aviso"))
        item = _destino(ctx, destino_id)
        if aviso in item.get("avisos", []):
            raise Conflicto("El destino ya tiene esa regla", codigo="REGLA_EXISTENTE")
        avisos = [*item.get("avisos", []), aviso]
        gestor.cambiar_filtro(item["suscripcion_arn"], _politica(ctx, avisos))
        evento = Evento("mensajeria.regla_creada", {"destino_id": item["destino_id"], "aviso": aviso})
        return 201, _vista({**item, "avisos": avisos}), [_guardar_avisos(ctx, item, avisos)], [evento]

    return _comando(peticion, ctx, "mensajeria.crear_regla", {"destino_id": destino_id, **cuerpo}, accion)


@app.ruta(f"DELETE {BASE}/destinos/{{destino_id}}/reglas/{{aviso}}", escritura=True)
def eliminar_regla(peticion):
    ctx = _ctx(peticion)
    destino_id, aviso = peticion.parametros["destino_id"], peticion.parametros["aviso"]
    gestor = _gestor()

    def accion():
        item = _destino(ctx, destino_id)
        if aviso not in item.get("avisos", []):
            raise NoEncontrado("El destino no tiene esa regla", codigo="REGLA_NO_ENCONTRADA")
        avisos = [a for a in item["avisos"] if a != aviso]
        if not avisos:
            raise Conflicto("Es la última regla del destino: elimina el destino en su lugar", codigo="ULTIMA_REGLA")
        gestor.cambiar_filtro(item["suscripcion_arn"], _politica(ctx, avisos))
        evento = Evento("mensajeria.regla_eliminada", {"destino_id": item["destino_id"], "aviso": aviso})
        return 200, _vista({**item, "avisos": avisos}), [_guardar_avisos(ctx, item, avisos)], [evento]

    return _comando(peticion, ctx, "mensajeria.eliminar_regla", {"destino_id": destino_id, "aviso": aviso}, accion)


@app.ruta(f"GET {BASE}/destinos/{{destino_id}}/mensajes")
def mensajes_destino(peticion):
    ctx = _ctx(peticion)
    item = _destino(ctx, peticion.parametros["destino_id"])
    if item["tipo"] != "cola":
        raise Validacion("Solo los destinos de tipo cola guardan mensajes para revisar", codigo="DESTINO_SIN_COLA")
    return 200, {"destino_id": item["destino_id"], "mensajes": _gestor().ver_mensajes(item["cola_nombre"])}


# --- prueba de distribución ---------------------------------------------------------------------------

@app.ruta(f"POST {BASE}/pruebas", escritura=True)
def prueba(peticion):
    ctx = _ctx(peticion)
    cuerpo = peticion.json()
    gestor = _gestor()

    def accion():
        aviso = M.validar_aviso(cuerpo.get("aviso"))
        atributos = M.atributos_aviso(aviso, ctx.tenant_id, ctx.local_id, prueba=True)
        titulo = M.AVISOS[aviso].titulo
        mensaje_id = gestor.publicar(f"MISE (prueba): {titulo}",
                                     f"Mensaje de prueba del aviso «{titulo}» para el local {ctx.local_id}. "
                                     f"Lo envió {ctx.usuario_nombre or ctx.usuario_id} desde Administración → Mensajería.",
                                     atributos)
        esperados = [{"destino_id": d["destino_id"], "nombre": d["nombre"], "tipo": d["tipo"]}
                     for d in _destinos(ctx) if M.recibe(_politica(ctx, d.get("avisos", [])), atributos)]
        respuesta = {"aviso": aviso, "mensaje_id": mensaje_id, "atributos": atributos, "destinos_esperados": esperados,
                     "explicacion": f"Lo reciben los destinos de este local con la regla «{titulo}». "
                                    f"Los demás no, porque su filtro no incluye ese aviso."}
        evento = Evento("mensajeria.prueba_enviada", {"aviso": aviso, "mensaje_id": mensaje_id,
                                                      "destinos_esperados": [d["destino_id"] for d in esperados]})
        return 200, respuesta, [], [evento]

    return _comando(peticion, ctx, "mensajeria.prueba", cuerpo, accion)


# --- mensajes fallidos ----------------------------------------------------------------------------------

def _es_del_local(ctx, canal: str, cuerpo) -> bool:
    if not isinstance(cuerpo, dict):
        return False
    if canal == "dte-emision":
        return cuerpo.get("tenant_id") == ctx.tenant_id and cuerpo.get("local_id") == ctx.local_id
    # contingencia: el mensaje trae el local y quién lo envió; el cliente sale de su membresía.
    if cuerpo.get("local_id") != ctx.local_id or not isinstance(cuerpo.get("sub"), str):
        return False
    return aws.almacen().membresia(cuerpo["sub"], ctx.tenant_id, ctx.local_id) is not None


def _resumen(canal: str, cuerpo: dict) -> str:
    if canal == "dte-emision":
        return f"Documento tributario de la venta {cuerpo.get('venta_id')}"
    mesa = (cuerpo.get("cuerpo") or {}).get("mesa_id") or (cuerpo.get("grupo") or "").split("#")[-1]
    return f"Comanda {cuerpo.get('operacion')} de la mesa {mesa}, registrada por {cuerpo.get('nombre') or cuerpo.get('sub')}"


def _diagnosticos(ctx) -> list[dict]:
    filas = aws.almacen().listar(OP, claves.fallos(ctx.L), "FALLO#", consistente=True)
    return sorted(({k: v for k, v in f.items() if k not in ("PK", "SK", "tipo_item", "expira_en")} for f in filas),
                  key=lambda f: f["registrado_en"], reverse=True)


@app.ruta(f"GET {BASE}/fallidos")
def fallidos(peticion):
    ctx = _ctx(peticion)
    gestor = _gestor()
    diagnosticos = _diagnosticos(ctx)
    ultimo = {}
    for d in diagnosticos:  # ya vienen del más nuevo al más antiguo
        ultimo.setdefault(d["mensaje_id"], d)
    apartados = []
    for canal_id in M.COLAS_CON_REPROCESO:
        canal = M.CANALES[canal_id]
        for m in gestor.mensajes_fallidos(M.CANALES[canal.fallidos].nombre_aws):
            if not _es_del_local(ctx, canal_id, m["cuerpo"]):
                continue
            apartados.append({"canal": canal_id, "cola_fallidos": canal.fallidos, "mensaje_id": m["mensaje_id"],
                              "resumen": _resumen(canal_id, m["cuerpo"]), "enviado_en": m["enviado_en"],
                              "cuerpo": m["cuerpo"], "diagnostico": ultimo.get(m["mensaje_id"])})
    return 200, {"fallidos": apartados, "errores_recientes": diagnosticos[:50]}


def _accion_fallido(peticion, nombre: str, reprocesar: bool):
    ctx = _ctx(peticion)
    mensaje_id = peticion.parametros["mensaje_id"]
    cuerpo = peticion.json()
    gestor = _gestor()

    def accion():
        canal_id = M.validar_canal_reproceso(cuerpo.get("canal"))
        canal = M.CANALES[canal_id]
        cola_fallidos = M.CANALES[canal.fallidos].nombre_aws
        mensaje = gestor.tomar(cola_fallidos, mensaje_id)
        if mensaje is None or not _es_del_local(ctx, canal_id, mensaje["cuerpo"]):
            if mensaje is not None:
                gestor.soltar(cola_fallidos, mensaje["recibo"])
            raise NoEncontrado("El mensaje ya no está en la cola de fallidos", codigo="MENSAJE_NO_ENCONTRADO")
        respuesta = {"mensaje_id": mensaje_id, "canal": canal_id}
        if reprocesar:
            respuesta.update({"estado": "reenviado", "nuevo_mensaje_id": gestor.reenviar(canal.nombre_aws, mensaje, fifo=canal.fifo)})
        else:
            respuesta["estado"] = "descartado"
        gestor.borrar(cola_fallidos, mensaje["recibo"])
        tipo = "mensajeria.fallido_reprocesado" if reprocesar else "mensajeria.fallido_descartado"
        return 200, respuesta, [], [Evento(tipo, {"mensaje_id": mensaje_id, "canal": canal_id,
                                                  "resumen": _resumen(canal_id, mensaje["cuerpo"])})]

    return _comando(peticion, ctx, nombre, {"mensaje_id": mensaje_id, **cuerpo}, accion)


@app.ruta(f"POST {BASE}/fallidos/{{mensaje_id}}/reprocesar", escritura=True)
def reprocesar(peticion):
    return _accion_fallido(peticion, "mensajeria.reprocesar_fallido", True)


@app.ruta(f"POST {BASE}/fallidos/{{mensaje_id}}/descartar", escritura=True)
def descartar(peticion):
    return _accion_fallido(peticion, "mensajeria.descartar_fallido", False)


lambda_handler = app
