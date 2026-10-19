"""Salón: plano de mesas, carta, bloqueo de mesas y garzón asignado.

Reemplaza a PATCH /api/mesas/{id} del local, que dejaba a cualquier rol cambiar cualquier campo y
liberar una mesa con pedido abierto (D4). Aquí:
- la estructura (número, capacidad, sector) se edita en administración;
- bloquear o desbloquear exige que la mesa no tenga pedido;
- el garzón asignado debe ser una persona activa del local.
"""

from pos_dominio import claves, roles, validacion as v, vistas
from pos_dominio.cambios import Evento, Resultado
from pos_dominio.errores import Conflicto, NoEncontrado, Validacion
from pos_dominio.modelos import MesaEstado
from pos_dominio.operaciones.base import Operacion
from pos_dominio.operaciones.pedidos import guardar_mesa


def plano(estructuras: list[dict], sectores: list[dict], estados: list[dict], *, solo_estado: bool = False) -> dict:
    """Vista del plano: estructura (configuracion) unida al estado (operacion) de cada mesa."""
    por_mesa = {e["mesa_id"]: e for e in estados}
    mesas = []
    for estructura in sorted(estructuras, key=lambda m: (m.get("sector_nombre", ""), m.get("numero", 0))):
        if not estructura.get("activa", True):
            continue
        estado = por_mesa.get(estructura["mesa_id"], {})
        mesa = {"mesa_id": estructura["mesa_id"], "estado": estado.get("estado", "libre"),
                "pedido_id": estado.get("pedido_id"), "garzon_id": estado.get("garzon_id")}
        if not solo_estado:
            mesa.update({"sector_id": estructura["sector_id"], "sector_nombre": estructura.get("sector_nombre"),
                         "numero": estructura["numero"], "capacidad": estructura["capacidad"]})
        mesas.append(mesa)
    respuesta = {"mesas": mesas}
    if not solo_estado:
        respuesta["sectores"] = [{"sector_id": s["sector_id"], "nombre": s["nombre"], "activo": s.get("activo", True)}
                                 for s in sorted(sectores, key=lambda s: s["nombre"])]
    return respuesta


def carta(productos: list[dict], version: int) -> dict:
    return {"version": version, "productos": [
        {k: p.get(k) for k in ("producto_id", "nombre", "categoria", "precio", "cuarto_id", "activo", "descripcion",
                               "modificadores")}
        for p in sorted(productos, key=lambda p: (p["categoria"], p["nombre"]))]}


def leer_mesa(almacen, ctx, cuerpo):
    datos = v.objeto(cuerpo)
    mesa_id = v.identificador(datos, "mesa_id")
    garzon_id = datos.get("garzon_id")
    return {"mesa_id": mesa_id, "estructura": almacen.mesa_estructura(ctx.L, mesa_id),
            "estado": almacen.mesa_estado(ctx.L, mesa_id),
            "garzon": almacen.membresia(garzon_id, ctx.tenant_id, ctx.local_id)
            if isinstance(garzon_id, str) and garzon_id else None}


def _mesa(estado) -> MesaEstado:
    estructura = estado["estructura"]
    if estructura is None or not estructura.activa:
        raise NoEncontrado("Mesa no encontrada", codigo="MESA_NO_ENCONTRADA")
    return estado["estado"] or MesaEstado(mesa_id=estado["mesa_id"])


def decidir_bloqueo(estado, ctx, cuerpo) -> Resultado:
    bloquear = v.booleano(cuerpo, "bloqueada", requerido=True)
    mesa = _mesa(estado)
    if bloquear == (mesa.estado == "bloqueada"):
        return Resultado(vistas.mesa(mesa))
    if bloquear and mesa.pedido_id:
        raise Conflicto("La mesa tiene un pedido abierto", codigo="MESA_CON_PEDIDO")
    mesa.estado = "bloqueada" if bloquear else "libre"
    return Resultado(vistas.mesa(mesa), cambios=[guardar_mesa(ctx, mesa)],
                     eventos=[Evento("mesa.bloqueada" if bloquear else "mesa.desbloqueada", {"mesa_id": mesa.mesa_id})])


def decidir_asignar_garzon(estado, ctx, cuerpo) -> Resultado:
    garzon_id = cuerpo.get("garzon_id")
    if garzon_id is not None:
        garzon_id = v.identificador(cuerpo, "garzon_id")
        garzon = estado["garzon"]
        if garzon is None or not garzon.activa or not roles.permitido(garzon.rol, "pedido.escribir"):
            raise Validacion("La persona elegida no atiende mesas en este local", codigo="GARZON_INVALIDO")
    mesa = _mesa(estado)
    if mesa.garzon_id == garzon_id:
        return Resultado(vistas.mesa(mesa))
    mesa.garzon_id = garzon_id
    return Resultado(vistas.mesa(mesa), cambios=[guardar_mesa(ctx, mesa)],
                     eventos=[Evento("mesa.garzon_asignado", {"mesa_id": mesa.mesa_id, "garzon_id": garzon_id})])


BLOQUEO = Operacion("salon.bloqueo", "mesa.gestionar", leer_mesa, decidir_bloqueo)
ASIGNAR_GARZON = Operacion("salon.asignar_garzon", "mesa.gestionar", leer_mesa, decidir_asignar_garzon)

# Claves usadas por las lecturas del salón
PREFIJO_MESA = "MESA#"
PREFIJO_SECTOR = "SECTOR#"
PREFIJO_PRODUCTO = "PROD#"
SK_CATALOGO = claves.SK_CATALOGO
