"""Administración del local: sectores, mesas, catálogo, cuartos, impresoras, inventario, recetas,
configuración, personal, código de autorización propio y estaciones de caja.

Todo vive en la tabla `configuracion`; el CMD y el evento de auditoría van en `operacion`, en la
misma transacción (DynamoDB permite transacciones entre tablas de la misma cuenta y región).

Correcciones respecto del local:
D14 los modificadores tienen ID estable (editarlos ya no rompe ítems vendidos) · D15 duplicados =
409, no 500 · D16 solo un dueño otorga o modifica el rol dueño, y nadie cambia su propio rol ·
las personas no se borran: se archivan (conserva la auditoría).
"""

from pos_dominio import autorizacion, claves, roles, validacion as v
from pos_dominio.cambios import Borrar, Crear, Evento, Guardar, Resultado, Sumar
from pos_dominio.errores import Conflicto, NoEncontrado, Prohibido, Validacion
from pos_dominio.modelos import ROLES
from pos_dominio.operaciones.base import Operacion, reemplazar

CFG = claves.TABLA_CONFIGURACION
CATEGORIAS = ("Entradas", "Fondos", "Bebidas", "Postres")
UNIDADES = ("kg", "g", "l", "ml", "unidad")
MAX_MESAS_POR_SECTOR = 90
_INTERNOS = {"PK", "SK", "GSI1PK", "GSI1SK", "tipo_item", "pin_hash", "pin_sal", "pin_iter", "clave_hash",
             "clave_sal", "clave_iter"}


def limpiar(item: dict | None) -> dict | None:
    """Vista para la API: sin claves internas ni hashes."""
    if item is None:
        return None
    return {k: val for k, val in item.items() if k not in _INTERNOS}


def _normalizar(nombre: str) -> str:
    return " ".join(nombre.lower().split())


def _guardar(ctx, sk: str, atributos: dict, version: int) -> Guardar:
    return Guardar(tabla=CFG, pk=ctx.L, sk=sk, atributos=atributos, version_leida=version)


def _unico(ctx, tipo: str, valor, ref_id: str, mensaje: str) -> Crear:
    return Crear(tabla=CFG, pk=ctx.L, sk=f"UNICO#{tipo}#{valor}", atributos={"tipo_item": "UNICO", "ref_id": ref_id},
                 al_fallar=Conflicto(mensaje, codigo="DUPLICADO"))


def _soltar(ctx, tipo: str, valor) -> Borrar:
    return Borrar(tabla=CFG, pk=ctx.L, sk=f"UNICO#{tipo}#{valor}")


def _evento(tipo: str, datos: dict) -> Evento:
    return Evento(tipo, limpiar(datos))


def _exigir(item, mensaje: str, codigo: str) -> dict:
    if item is None:
        raise NoEncontrado(mensaje, codigo=codigo)
    return item


def _obtener(almacen, ctx, sk: str) -> dict | None:
    return almacen.obtener(CFG, ctx.L, sk, consistente=True)


# --- sectores ------------------------------------------------------------------------------------------

def leer_sector(almacen, ctx, cuerpo):
    datos = v.objeto(cuerpo)
    sector_id = v.identificador(datos, "sector_id", requerido=False)
    if sector_id is None:
        return {"sector": None, "mesas": []}
    return {"sector": _obtener(almacen, ctx, f"SECTOR#{sector_id}"),
            "mesas": [m for m in almacen.listar(CFG, ctx.L, "MESA#", consistente=True) if m["sector_id"] == sector_id]}


def decidir_crear_sector(estado, ctx, cuerpo) -> Resultado:
    nombre = v.texto(cuerpo, "nombre", max_largo=60)
    sector = {"tipo_item": "SECTOR", "sector_id": ctx.nuevo_id(), "nombre": nombre,
              "activo": v.booleano(cuerpo, "activo", defecto=True)}
    return Resultado(limpiar(sector), http=201, cambios=[
        _guardar(ctx, f"SECTOR#{sector['sector_id']}", sector, 0),
        _unico(ctx, "SECTOR", _normalizar(nombre), sector["sector_id"], "Ya existe un sector con ese nombre"),
    ], eventos=[_evento("sector.creado", sector)])


def decidir_editar_sector(estado, ctx, cuerpo) -> Resultado:
    sector = dict(_exigir(estado["sector"], "Sector no encontrado", "SECTOR_NO_ENCONTRADO"))
    version = sector.pop("version", 0)
    cambios = []
    if "nombre" in cuerpo:
        nombre = v.texto(cuerpo, "nombre", max_largo=60)
        if _normalizar(nombre) != _normalizar(sector["nombre"]):
            cambios += [_soltar(ctx, "SECTOR", _normalizar(sector["nombre"])),
                        _unico(ctx, "SECTOR", _normalizar(nombre), sector["sector_id"], "Ya existe un sector con ese nombre")]
        if nombre != sector["nombre"]:
            if len(estado["mesas"]) > MAX_MESAS_POR_SECTOR:
                raise Validacion("El sector tiene demasiadas mesas para renombrarlo de una vez", codigo="SECTOR_GRANDE")
            for mesa in estado["mesas"]:
                # El nombre del sector va copiado en cada mesa para leer el plano sin unir tablas.
                cambios.append(reemplazar(CFG, ctx.L, mesa["SK"], {**mesa, "sector_nombre": nombre}))
        sector["nombre"] = nombre
    if "activo" in cuerpo:
        sector["activo"] = v.booleano(cuerpo, "activo", requerido=True)
    cambios.insert(0, _guardar(ctx, f"SECTOR#{sector['sector_id']}", sector, version))
    return Resultado(limpiar(sector), cambios=cambios, eventos=[_evento("sector.editado", sector)])


# --- mesas -----------------------------------------------------------------------------------------------

def leer_mesa(almacen, ctx, cuerpo):
    datos = v.objeto(cuerpo)
    mesa_id = v.identificador(datos, "mesa_id", requerido=False)
    mesa = _obtener(almacen, ctx, f"MESA#{mesa_id}") if mesa_id else None
    sector_id = v.identificador(datos, "sector_id", requerido=False) or (mesa or {}).get("sector_id")
    return {"mesa": mesa, "sector": _obtener(almacen, ctx, f"SECTOR#{sector_id}") if sector_id else None,
            "estado": almacen.mesa_estado(ctx.L, mesa_id) if mesa_id else None}


def _sector_valido(estado) -> dict:
    sector = _exigir(estado["sector"], "Sector no encontrado", "SECTOR_NO_ENCONTRADO")
    if not sector.get("activo", True):
        raise Validacion("El sector está inactivo", codigo="SECTOR_INACTIVO")
    return sector


def decidir_crear_mesa(estado, ctx, cuerpo) -> Resultado:
    numero = v.entero(cuerpo, "numero", minimo=1, maximo=9999)
    capacidad = v.entero(cuerpo, "capacidad", requerido=False, defecto=4, minimo=1, maximo=100)
    sector = _sector_valido(estado)
    mesa = {"tipo_item": "MESA", "mesa_id": ctx.nuevo_id(), "sector_id": sector["sector_id"],
            "sector_nombre": sector["nombre"], "numero": numero, "capacidad": capacidad, "activa": True}
    return Resultado(limpiar(mesa), http=201, cambios=[
        _guardar(ctx, f"MESA#{mesa['mesa_id']}", mesa, 0),
        _unico(ctx, "MESA", f"{sector['sector_id']}#{numero}", mesa["mesa_id"], "Ya existe una mesa con ese número en el sector"),
    ], eventos=[_evento("mesa.creada", mesa)])


def decidir_editar_mesa(estado, ctx, cuerpo) -> Resultado:
    mesa = dict(_exigir(estado["mesa"], "Mesa no encontrada", "MESA_NO_ENCONTRADA"))
    version = mesa.pop("version", 0)
    anterior = (mesa["sector_id"], mesa["numero"])
    if "numero" in cuerpo:
        mesa["numero"] = v.entero(cuerpo, "numero", minimo=1, maximo=9999)
    if "capacidad" in cuerpo:
        mesa["capacidad"] = v.entero(cuerpo, "capacidad", minimo=1, maximo=100)
    if "sector_id" in cuerpo and cuerpo["sector_id"] != mesa["sector_id"]:
        sector = _sector_valido(estado)
        mesa["sector_id"], mesa["sector_nombre"] = sector["sector_id"], sector["nombre"]
    if "activa" in cuerpo:
        mesa["activa"] = v.booleano(cuerpo, "activa", requerido=True)
        mesa_estado = estado["estado"]
        if not mesa["activa"] and mesa_estado is not None and mesa_estado.pedido_id:
            raise Conflicto("La mesa tiene un pedido abierto", codigo="MESA_CON_PEDIDO")
    cambios = [_guardar(ctx, f"MESA#{mesa['mesa_id']}", mesa, version)]
    if (mesa["sector_id"], mesa["numero"]) != anterior:
        cambios += [_soltar(ctx, "MESA", f"{anterior[0]}#{anterior[1]}"),
                    _unico(ctx, "MESA", f"{mesa['sector_id']}#{mesa['numero']}", mesa["mesa_id"],
                           "Ya existe una mesa con ese número en el sector")]
    return Resultado(limpiar(mesa), cambios=cambios, eventos=[_evento("mesa.editada", mesa)])


# --- catálogo ------------------------------------------------------------------------------------------

def leer_producto(almacen, ctx, cuerpo):
    datos = v.objeto(cuerpo)
    producto_id = v.identificador(datos, "producto_id", requerido=False)
    return {"producto": _obtener(almacen, ctx, f"PROD#{producto_id}") if producto_id else None,
            "cuartos": {c["cuarto_id"]: c for c in almacen.listar(CFG, ctx.L, "CUARTO#", consistente=True)}}


def _modificadores(cuerpo, actuales: list[dict], ctx) -> list[dict]:
    """Reemplaza la lista completa (como el formulario del local), pero conserva el ID de cada
    modificador que ya existía (D14)."""
    existentes = {m["modificador_id"] for m in actuales}
    resultado = []
    for i, dato in enumerate(v.lista(cuerpo, "modificadores", requerido=False, maximo=30)):
        dato = v.objeto(dato, f"modificadores[{i}]")
        modificador_id = dato.get("modificador_id")
        if modificador_id is not None and modificador_id not in existentes:
            raise Validacion("Modificador desconocido", codigo="MODIFICADOR_INVALIDO", detalle={"indice": i})
        resultado.append({"modificador_id": modificador_id or ctx.nuevo_id(),
                          "nombre": v.texto(dato, "nombre", max_largo=60),
                          "precio_adicional": v.entero(dato, "precio_adicional", requerido=False, defecto=0,
                                                       minimo=0, maximo=10_000_000)})
    return resultado


def _cuarto_valido(estado, cuarto_id: str) -> None:
    if cuarto_id not in estado["cuartos"]:
        raise NoEncontrado("Cuarto de cocina no encontrado", codigo="CUARTO_NO_ENCONTRADO")


def _subir_catalogo(ctx) -> Sumar:
    # La PWA guarda la carta y solo la vuelve a pedir si cambió esta versión.
    return Sumar(tabla=CFG, pk=ctx.L, sk=claves.SK_CATALOGO, incrementos={})


def decidir_crear_producto(estado, ctx, cuerpo) -> Resultado:
    producto = {
        "tipo_item": "PRODUCTO", "producto_id": ctx.nuevo_id(), "nombre": v.texto(cuerpo, "nombre", max_largo=100),
        "categoria": v.uno_de(cuerpo, "categoria", CATEGORIAS), "precio": v.entero(cuerpo, "precio", minimo=0,
                                                                                   maximo=100_000_000),
        "cuarto_id": v.identificador(cuerpo, "cuarto_id"), "activo": v.booleano(cuerpo, "activo", defecto=True),
        "descripcion": v.texto(cuerpo, "descripcion", requerido=False, max_largo=500),
    }
    _cuarto_valido(estado, producto["cuarto_id"])
    producto["modificadores"] = _modificadores(cuerpo, [], ctx)
    producto = {k: val for k, val in producto.items() if val is not None}
    return Resultado(limpiar(producto), http=201,
                     cambios=[_guardar(ctx, f"PROD#{producto['producto_id']}", producto, 0), _subir_catalogo(ctx)],
                     eventos=[_evento("catalogo.producto_creado", producto)])


def decidir_editar_producto(estado, ctx, cuerpo) -> Resultado:
    producto = dict(_exigir(estado["producto"], "Producto no encontrado", "PRODUCTO_NO_ENCONTRADO"))
    version = producto.pop("version", 0)
    if "nombre" in cuerpo:
        producto["nombre"] = v.texto(cuerpo, "nombre", max_largo=100)
    if "categoria" in cuerpo:
        producto["categoria"] = v.uno_de(cuerpo, "categoria", CATEGORIAS)
    if "precio" in cuerpo:
        producto["precio"] = v.entero(cuerpo, "precio", minimo=0, maximo=100_000_000)
    if "cuarto_id" in cuerpo:
        producto["cuarto_id"] = v.identificador(cuerpo, "cuarto_id")
        _cuarto_valido(estado, producto["cuarto_id"])
    if "activo" in cuerpo:
        producto["activo"] = v.booleano(cuerpo, "activo", requerido=True)
    if "descripcion" in cuerpo:
        descripcion = v.texto(cuerpo, "descripcion", requerido=False, max_largo=500)
        producto.pop("descripcion", None)
        if descripcion:
            producto["descripcion"] = descripcion
    if "modificadores" in cuerpo:
        producto["modificadores"] = _modificadores(cuerpo, producto.get("modificadores", []), ctx)
    return Resultado(limpiar(producto),
                     cambios=[_guardar(ctx, f"PROD#{producto['producto_id']}", producto, version), _subir_catalogo(ctx)],
                     eventos=[_evento("catalogo.producto_editado", producto)])


# --- cuartos e impresoras ----------------------------------------------------------------------------

def leer_cuarto(almacen, ctx, cuerpo):
    datos = v.objeto(cuerpo)
    cuarto_id = v.identificador(datos, "cuarto_id", requerido=False)
    return {"cuarto": _obtener(almacen, ctx, f"CUARTO#{cuarto_id}") if cuarto_id else None,
            "impresoras": {i["impresora_id"] for i in almacen.listar(CFG, ctx.L, "IMPRESORA#", consistente=True)}}


def _impresora_de_cuarto(estado, cuerpo):
    impresora_id = cuerpo.get("impresora_id")
    if impresora_id is None:
        return None
    impresora_id = v.identificador(cuerpo, "impresora_id")
    if impresora_id not in estado["impresoras"]:
        raise NoEncontrado("Impresora no encontrada", codigo="IMPRESORA_NO_ENCONTRADA")
    return impresora_id


def decidir_crear_cuarto(estado, ctx, cuerpo) -> Resultado:
    nombre = v.texto(cuerpo, "nombre", max_largo=60)
    cuarto = {"tipo_item": "CUARTO", "cuarto_id": ctx.nuevo_id(), "nombre": nombre,
              "descripcion": v.texto(cuerpo, "descripcion", requerido=False, defecto="", max_largo=200, vacio=True),
              "activo": v.booleano(cuerpo, "activo", defecto=True), "impresora_id": _impresora_de_cuarto(estado, cuerpo)}
    cuarto = {k: val for k, val in cuarto.items() if val is not None}
    return Resultado(limpiar(cuarto), http=201, cambios=[
        _guardar(ctx, f"CUARTO#{cuarto['cuarto_id']}", cuarto, 0),
        _unico(ctx, "CUARTO", _normalizar(nombre), cuarto["cuarto_id"], "Ya existe un cuarto con ese nombre"),
    ], eventos=[_evento("cuarto.creado", cuarto)])


def decidir_editar_cuarto(estado, ctx, cuerpo) -> Resultado:
    cuarto = dict(_exigir(estado["cuarto"], "Cuarto no encontrado", "CUARTO_NO_ENCONTRADO"))
    version = cuarto.pop("version", 0)
    cambios = []
    if "nombre" in cuerpo:
        nombre = v.texto(cuerpo, "nombre", max_largo=60)
        if _normalizar(nombre) != _normalizar(cuarto["nombre"]):
            cambios += [_soltar(ctx, "CUARTO", _normalizar(cuarto["nombre"])),
                        _unico(ctx, "CUARTO", _normalizar(nombre), cuarto["cuarto_id"], "Ya existe un cuarto con ese nombre")]
        cuarto["nombre"] = nombre
    if "descripcion" in cuerpo:
        cuarto["descripcion"] = v.texto(cuerpo, "descripcion", requerido=False, defecto="", max_largo=200, vacio=True)
    if "activo" in cuerpo:
        cuarto["activo"] = v.booleano(cuerpo, "activo", requerido=True)
    if "impresora_id" in cuerpo:
        cuarto.pop("impresora_id", None)
        impresora_id = _impresora_de_cuarto(estado, cuerpo)
        if impresora_id:
            cuarto["impresora_id"] = impresora_id
    cambios.insert(0, _guardar(ctx, f"CUARTO#{cuarto['cuarto_id']}", cuarto, version))
    return Resultado(limpiar(cuarto), cambios=cambios, eventos=[_evento("cuarto.editado", cuarto)])


def leer_impresora(almacen, ctx, cuerpo):
    impresora_id = v.identificador(v.objeto(cuerpo), "impresora_id", requerido=False)
    return {"impresora": _obtener(almacen, ctx, f"IMPRESORA#{impresora_id}") if impresora_id else None}


def _con_clave(impresora: dict) -> tuple[dict, str]:
    clave = autorizacion.nueva_clave_impresora()
    impresora["clave_hash"], impresora["clave_sal"] = autorizacion.hashear_clave_impresora(clave)
    impresora["clave_iter"] = 0
    return impresora, clave


def decidir_crear_impresora(estado, ctx, cuerpo) -> Resultado:
    impresora = {"tipo_item": "IMPRESORA", "impresora_id": ctx.nuevo_id(),
                 "nombre": v.texto(cuerpo, "nombre", max_largo=60),
                 "modelo": v.texto(cuerpo, "modelo", requerido=False, defecto="", max_largo=60, vacio=True),
                 "protocolo": "cloudprnt", "activa": v.booleano(cuerpo, "activa", defecto=True)}
    impresora, clave = _con_clave(impresora)
    # La clave se muestra UNA vez. El CMD guarda esta respuesta 48 h para reintentos idempotentes.
    respuesta = {**limpiar(impresora), "clave": clave, "usuario_cloudprnt": impresora["impresora_id"]}
    return Resultado(respuesta, http=201, cambios=[_guardar(ctx, f"IMPRESORA#{impresora['impresora_id']}", impresora, 0)],
                     eventos=[_evento("impresora.creada", impresora)])


def decidir_editar_impresora(estado, ctx, cuerpo) -> Resultado:
    impresora = dict(_exigir(estado["impresora"], "Impresora no encontrada", "IMPRESORA_NO_ENCONTRADA"))
    version = impresora.pop("version", 0)
    if "nombre" in cuerpo:
        impresora["nombre"] = v.texto(cuerpo, "nombre", max_largo=60)
    if "modelo" in cuerpo:
        impresora["modelo"] = v.texto(cuerpo, "modelo", requerido=False, defecto="", max_largo=60, vacio=True)
    if "activa" in cuerpo:
        impresora["activa"] = v.booleano(cuerpo, "activa", requerido=True)
    return Resultado(limpiar(impresora), cambios=[_guardar(ctx, f"IMPRESORA#{impresora['impresora_id']}", impresora, version)],
                     eventos=[_evento("impresora.editada", impresora)])


def decidir_rotar_clave(estado, ctx, cuerpo) -> Resultado:
    impresora = dict(_exigir(estado["impresora"], "Impresora no encontrada", "IMPRESORA_NO_ENCONTRADA"))
    version = impresora.pop("version", 0)
    impresora, clave = _con_clave(impresora)
    return Resultado({**limpiar(impresora), "clave": clave, "usuario_cloudprnt": impresora["impresora_id"]},
                     cambios=[_guardar(ctx, f"IMPRESORA#{impresora['impresora_id']}", impresora, version)],
                     eventos=[_evento("impresora.clave_rotada", {"impresora_id": impresora["impresora_id"]})])


# --- inventario ----------------------------------------------------------------------------------------

def leer_materia_prima(almacen, ctx, cuerpo):
    mp_id = v.identificador(v.objeto(cuerpo), "materia_prima_id", requerido=False)
    return {"materia_prima": _obtener(almacen, ctx, f"MP#{mp_id}") if mp_id else None}


def decidir_crear_materia_prima(estado, ctx, cuerpo) -> Resultado:
    mp = {"tipo_item": "MATERIA_PRIMA", "materia_prima_id": ctx.nuevo_id(),
          "nombre": v.texto(cuerpo, "nombre", max_largo=100), "unidad": v.uno_de(cuerpo, "unidad", UNIDADES),
          "stock_actual_mil": v.milesimas(cuerpo, "stock_actual", requerido=False, defecto=0),
          "stock_minimo_mil": v.milesimas(cuerpo, "stock_minimo", requerido=False, defecto=0),
          "activo": v.booleano(cuerpo, "activo", defecto=True)}
    return Resultado(limpiar(mp), http=201, cambios=[_guardar(ctx, f"MP#{mp['materia_prima_id']}", mp, 0)],
                     eventos=[_evento("inventario.materia_prima_creada", mp)])


def decidir_editar_materia_prima(estado, ctx, cuerpo) -> Resultado:
    mp = dict(_exigir(estado["materia_prima"], "Materia prima no encontrada", "MATERIA_PRIMA_NO_ENCONTRADA"))
    version = mp.pop("version", 0)
    if "nombre" in cuerpo:
        mp["nombre"] = v.texto(cuerpo, "nombre", max_largo=100)
    if "unidad" in cuerpo:
        mp["unidad"] = v.uno_de(cuerpo, "unidad", UNIDADES)
    if "stock_actual" in cuerpo:
        mp["stock_actual_mil"] = v.milesimas(cuerpo, "stock_actual")
    if "stock_minimo" in cuerpo:
        mp["stock_minimo_mil"] = v.milesimas(cuerpo, "stock_minimo")
    if "activo" in cuerpo:
        mp["activo"] = v.booleano(cuerpo, "activo", requerido=True)
    return Resultado(limpiar(mp), cambios=[_guardar(ctx, f"MP#{mp['materia_prima_id']}", mp, version)],
                     eventos=[_evento("inventario.materia_prima_editada", mp)])


def leer_receta(almacen, ctx, cuerpo):
    producto_id = v.identificador(v.objeto(cuerpo), "producto_id")
    return {"producto": _obtener(almacen, ctx, f"PROD#{producto_id}"),
            "receta": _obtener(almacen, ctx, f"RECETA#{producto_id}"),
            "materias": {m["materia_prima_id"] for m in almacen.listar(CFG, ctx.L, "MP#", consistente=True)}}


def decidir_guardar_receta(estado, ctx, cuerpo) -> Resultado:
    producto = _exigir(estado["producto"], "Producto no encontrado", "PRODUCTO_NO_ENCONTRADO")
    ingredientes, vistos = [], set()
    for i, dato in enumerate(v.lista(cuerpo, "ingredientes", minimo=1, maximo=50)):
        dato = v.objeto(dato, f"ingredientes[{i}]")
        mp_id = v.identificador(dato, "materia_prima_id")
        cantidad = v.milesimas(dato, "cantidad")
        if cantidad <= 0:
            raise Validacion("La cantidad de cada ingrediente debe ser mayor a 0", codigo="CANTIDAD_INVALIDA")
        if mp_id not in estado["materias"]:
            raise NoEncontrado(f"Materia prima '{mp_id}' no encontrada", codigo="MATERIA_PRIMA_NO_ENCONTRADA")
        if mp_id in vistos:
            raise Validacion("No repitas la misma materia prima en una receta", codigo="INGREDIENTE_REPETIDO")
        vistos.add(mp_id)
        ingredientes.append({"materia_prima_id": mp_id, "cantidad_mil": cantidad})
    receta = {"tipo_item": "RECETA", "producto_id": producto["producto_id"], "ingredientes": ingredientes}
    version = (estado["receta"] or {}).get("version", 0)
    return Resultado(limpiar(receta), cambios=[_guardar(ctx, f"RECETA#{producto['producto_id']}", receta, version)],
                     eventos=[_evento("inventario.receta_guardada", receta)])


# --- configuración del local -----------------------------------------------------------------------------

def leer_local(almacen, ctx, cuerpo):
    return {"local": _obtener(almacen, ctx, claves.SK_LOCAL),
            "impresoras": {i["impresora_id"] for i in almacen.listar(CFG, ctx.L, "IMPRESORA#", consistente=True)}}


def decidir_editar_local(estado, ctx, cuerpo) -> Resultado:
    local = dict(_exigir(estado["local"], "Configuración del local no encontrada", "LOCAL_NO_ENCONTRADO"))
    version = local.pop("version", 0)
    if "nombre_local" in cuerpo:
        local["nombre_local"] = v.texto(cuerpo, "nombre_local", max_largo=100)
    if "marca" in cuerpo:
        local["marca"] = v.texto(cuerpo, "marca", max_largo=100)
    if "propina_sugerida_pct" in cuerpo:
        local["propina_sugerida_pct"] = v.entero(cuerpo, "propina_sugerida_pct", minimo=0, maximo=100)
    if "umbral_diferencia_pct" in cuerpo:
        # El local guardaba NUMERIC(5,2): hasta 2 decimales. Aquí, en puntos base enteros.
        milesimas = v.milesimas(cuerpo, "umbral_diferencia_pct", maximo=100_000)
        if milesimas % 10:
            raise Validacion("umbral_diferencia_pct admite hasta 2 decimales", codigo="CAMPO_INVALIDO")
        local["umbral_diferencia_pb"] = milesimas // 10
    if "umbral_diferencia_minimo" in cuerpo:
        local["umbral_diferencia_minimo"] = v.entero(cuerpo, "umbral_diferencia_minimo", minimo=0, maximo=100_000_000)
    if "impresora_caja_id" in cuerpo:
        local.pop("impresora_caja_id", None)
        if cuerpo["impresora_caja_id"] is not None:
            impresora_id = v.identificador(cuerpo, "impresora_caja_id")
            if impresora_id not in estado["impresoras"]:
                raise NoEncontrado("Impresora no encontrada", codigo="IMPRESORA_NO_ENCONTRADA")
            local["impresora_caja_id"] = impresora_id
    return Resultado(vista_local(local), cambios=[_guardar(ctx, claves.SK_LOCAL, local, version)],
                     eventos=[_evento("local.actualizado", local)])


def vista_local(local: dict) -> dict:
    vista = limpiar(local)
    vista["umbral_diferencia_pct"] = vista.get("umbral_diferencia_pb", 200) / 100
    return vista


# --- personal ---------------------------------------------------------------------------------------

def leer_invitar(almacen, ctx, cuerpo):
    email = claves.normalizar_email(v.objeto(cuerpo).get("email"))
    sub = almacen.email_a_sub(email)
    return {"email": email, "sub": sub,
            "membresia": almacen.membresia(sub, ctx.tenant_id, ctx.local_id) if sub else None,
            "invitacion": almacen.obtener(CFG, claves.invitacion(email), claves.sk_membresia(ctx.tenant_id, ctx.local_id))}


def _exigir_puede_otorgar(ctx, rol: str) -> None:
    if rol == "dueno":
        roles.exigir(ctx.rol, "admin.dueno")


def decidir_invitar(estado, ctx, cuerpo) -> Resultado:
    nombre = v.texto(cuerpo, "nombre", max_largo=80)
    rol = v.uno_de(cuerpo, "rol", ROLES)
    _exigir_puede_otorgar(ctx, rol)
    email, sub = estado["email"], estado["sub"]
    sk = claves.sk_membresia(ctx.tenant_id, ctx.local_id)
    base = {"tenant_id": ctx.tenant_id, "local_id": ctx.local_id, "rol": rol, "nombre": nombre, "email": email,
            "invitado_por": ctx.usuario_id, "creado_en": ctx.ahora_iso, "GSI1PK": claves.gsi_personal(ctx.L)}
    if sub:
        # La persona ya usa la plataforma (en otro local): se le crea la membresía directo.
        if estado["membresia"] is not None:
            raise Conflicto("Esa persona ya pertenece a este local", codigo="YA_ES_MIEMBRO")
        membresia = {**base, "tipo_item": "MEMBRESIA", "sub": sub, "estado": "activo", "GSI1SK": f"{nombre}#{sub}"}
        cambio = Guardar(tabla=CFG, pk=claves.usuario(sub), sk=sk, atributos=membresia, version_leida=0,
                         reintentar=False, al_fallar=Conflicto("Esa persona ya pertenece a este local", codigo="YA_ES_MIEMBRO"))
        return Resultado(limpiar(membresia), http=201, cambios=[cambio], eventos=[_evento("personal.agregado", membresia)])
    if estado["invitacion"] is not None:
        raise Conflicto("Ya hay una invitación para ese email en este local", codigo="INVITACION_EXISTENTE")
    invitacion = {**base, "tipo_item": "INVITACION", "estado": "invitado", "GSI1SK": f"{nombre}#INV#{email}"}
    cambio = Crear(tabla=CFG, pk=claves.invitacion(email), sk=sk, atributos=invitacion,
                   al_fallar=Conflicto("Ya hay una invitación para ese email en este local", codigo="INVITACION_EXISTENTE"))
    return Resultado(limpiar(invitacion), http=201, cambios=[cambio], eventos=[_evento("personal.invitado", invitacion)])


def leer_membresia(almacen, ctx, cuerpo):
    sub = v.identificador(v.objeto(cuerpo), "sub")
    return {"membresia": almacen.membresia(sub, ctx.tenant_id, ctx.local_id)}


def decidir_editar_personal(estado, ctx, cuerpo) -> Resultado:
    membresia = _exigir(estado["membresia"], "Persona no encontrada en este local", "PERSONA_NO_ENCONTRADA")
    atributos = membresia.a_atributos()
    version = atributos.pop("version", 0)
    nuevo_rol = v.uno_de(cuerpo, "rol", ROLES, requerido=False)
    nuevo_estado = v.uno_de(cuerpo, "estado", ("activo", "archivado"), requerido=False)
    if membresia.sub == ctx.usuario_id and (nuevo_rol or nuevo_estado):
        raise Prohibido("No puedes cambiar tu propio rol ni archivarte", codigo="CAMBIO_PROPIO")
    if membresia.rol == "dueno" or nuevo_rol == "dueno":
        roles.exigir(ctx.rol, "admin.dueno")
    if nuevo_rol:
        atributos["rol"] = nuevo_rol
    if nuevo_estado:
        atributos["estado"] = nuevo_estado
    if "nombre" in cuerpo:
        atributos["nombre"] = v.texto(cuerpo, "nombre", max_largo=80)
    atributos.update({"tipo_item": "MEMBRESIA", "GSI1PK": claves.gsi_personal(ctx.L),
                      "GSI1SK": f"{atributos['nombre']}#{membresia.sub}"})
    return Resultado(limpiar(atributos), cambios=[
        Guardar(tabla=CFG, pk=claves.usuario(membresia.sub), sk=claves.sk_membresia(ctx.tenant_id, ctx.local_id),
                atributos=atributos, version_leida=version)],
        eventos=[_evento("personal.editado", {"sub": membresia.sub, "rol": atributos["rol"], "estado": atributos["estado"]})])


def leer_invitacion(almacen, ctx, cuerpo):
    email = claves.normalizar_email(v.objeto(cuerpo).get("email"))
    return {"email": email, "invitacion": almacen.obtener(CFG, claves.invitacion(email),
                                                          claves.sk_membresia(ctx.tenant_id, ctx.local_id))}


def decidir_cancelar_invitacion(estado, ctx, cuerpo) -> Resultado:
    invitacion = _exigir(estado["invitacion"], "Invitación no encontrada", "INVITACION_NO_ENCONTRADA")
    _exigir_puede_otorgar(ctx, invitacion["rol"])
    return Resultado({"email": estado["email"], "cancelada": True}, cambios=[
        Borrar(tabla=CFG, pk=claves.invitacion(estado["email"]), sk=invitacion["SK"])],
        eventos=[_evento("personal.invitacion_cancelada", {"email": estado["email"]})])


def leer_propia(almacen, ctx, cuerpo):
    return {"membresia": almacen.membresia(ctx.usuario_id, ctx.tenant_id, ctx.local_id)}


def decidir_mi_codigo(estado, ctx, cuerpo) -> Resultado:
    codigo = autorizacion.validar_formato_codigo(cuerpo.get("codigo"))
    membresia = _exigir(estado["membresia"], "Membresía no encontrada", "PERSONA_NO_ENCONTRADA")
    atributos = membresia.a_atributos()
    version = atributos.pop("version", 0)
    atributos["pin_hash"], atributos["pin_sal"], atributos["pin_iter"] = autorizacion.hashear(codigo)
    atributos.update({"tipo_item": "MEMBRESIA", "GSI1PK": claves.gsi_personal(ctx.L),
                      "GSI1SK": f"{atributos['nombre']}#{membresia.sub}"})
    return Resultado({"actualizado": True}, cambios=[
        Guardar(tabla=CFG, pk=claves.usuario(membresia.sub), sk=claves.sk_membresia(ctx.tenant_id, ctx.local_id),
                atributos=atributos, version_leida=version)],
        eventos=[_evento("personal.codigo_definido", {"sub": membresia.sub})])


# --- estaciones de caja -------------------------------------------------------------------------------

def leer_estacion(almacen, ctx, cuerpo):
    estacion_id = v.identificador(v.objeto(cuerpo), "estacion_id", requerido=False)
    return {"estacion": _obtener(almacen, ctx, f"ESTACION#{estacion_id}") if estacion_id else None}


def decidir_crear_estacion(estado, ctx, cuerpo) -> Resultado:
    estacion = {"tipo_item": "ESTACION", "estacion_id": ctx.nuevo_id(), "nombre": v.texto(cuerpo, "nombre", max_largo=60),
                "tipo": "caja", "creada_por": ctx.usuario_id, "creada_en": ctx.ahora_iso}
    return Resultado(limpiar(estacion), http=201, cambios=[_guardar(ctx, f"ESTACION#{estacion['estacion_id']}", estacion, 0)],
                     eventos=[_evento("estacion.creada", estacion)])


def decidir_eliminar_estacion(estado, ctx, cuerpo) -> Resultado:
    estacion = _exigir(estado["estacion"], "Estación no encontrada", "ESTACION_NO_ENCONTRADA")
    return Resultado({"estacion_id": estacion["estacion_id"], "eliminada": True},
                     cambios=[Borrar(tabla=CFG, pk=ctx.L, sk=estacion["SK"])],
                     eventos=[_evento("estacion.eliminada", {"estacion_id": estacion["estacion_id"]})])


_E = "admin.estructura"
OPERACIONES = {
    ("sectores", "crear"): Operacion("admin.sector.crear", _E, leer_sector, decidir_crear_sector),
    ("sectores", "editar"): Operacion("admin.sector.editar", _E, leer_sector, decidir_editar_sector),
    ("mesas", "crear"): Operacion("admin.mesa.crear", _E, leer_mesa, decidir_crear_mesa),
    ("mesas", "editar"): Operacion("admin.mesa.editar", _E, leer_mesa, decidir_editar_mesa),
    ("productos", "crear"): Operacion("admin.producto.crear", _E, leer_producto, decidir_crear_producto),
    ("productos", "editar"): Operacion("admin.producto.editar", _E, leer_producto, decidir_editar_producto),
    ("cuartos", "crear"): Operacion("admin.cuarto.crear", _E, leer_cuarto, decidir_crear_cuarto),
    ("cuartos", "editar"): Operacion("admin.cuarto.editar", _E, leer_cuarto, decidir_editar_cuarto),
    ("impresoras", "crear"): Operacion("admin.impresora.crear", _E, leer_impresora, decidir_crear_impresora),
    ("impresoras", "editar"): Operacion("admin.impresora.editar", _E, leer_impresora, decidir_editar_impresora),
    ("impresoras", "rotar-clave"): Operacion("admin.impresora.rotar_clave", _E, leer_impresora, decidir_rotar_clave),
    ("materias-primas", "crear"): Operacion("admin.mp.crear", _E, leer_materia_prima, decidir_crear_materia_prima),
    ("materias-primas", "editar"): Operacion("admin.mp.editar", _E, leer_materia_prima, decidir_editar_materia_prima),
    ("recetas", "editar"): Operacion("admin.receta.guardar", _E, leer_receta, decidir_guardar_receta),
    ("configuracion", "editar"): Operacion("admin.local.editar", _E, leer_local, decidir_editar_local),
    ("personal", "crear"): Operacion("admin.personal.invitar", "admin.personal", leer_invitar, decidir_invitar),
    ("personal", "editar"): Operacion("admin.personal.editar", "admin.personal", leer_membresia, decidir_editar_personal),
    ("invitaciones", "eliminar"): Operacion("admin.invitacion.cancelar", "admin.personal", leer_invitacion,
                                            decidir_cancelar_invitacion),
    ("mi-codigo", "crear"): Operacion("admin.mi_codigo", "autorizar", leer_propia, decidir_mi_codigo),
    ("estaciones", "crear"): Operacion("admin.estacion.crear", _E, leer_estacion, decidir_crear_estacion),
    ("estaciones", "eliminar"): Operacion("admin.estacion.eliminar", _E, leer_estacion, decidir_eliminar_estacion),
}

# Nombre del campo que recibe el {id} de la ruta en cada recurso.
CAMPO_ID = {"sectores": "sector_id", "mesas": "mesa_id", "productos": "producto_id", "cuartos": "cuarto_id",
            "impresoras": "impresora_id", "materias-primas": "materia_prima_id", "recetas": "producto_id",
            "personal": "sub", "invitaciones": "email", "estaciones": "estacion_id"}

# Listados: prefijo de SK en la partición del local (configuracion).
LISTADOS = {"sectores": "SECTOR#", "mesas": "MESA#", "productos": "PROD#", "cuartos": "CUARTO#",
            "impresoras": "IMPRESORA#", "materias-primas": "MP#", "recetas": "RECETA#", "estaciones": "ESTACION#"}
