"""Herramienta TEMPORAL `semilla`: carga un local de demostración con datos mock en una sola invocación.

Se crea desde la consola, se ejecuta una vez con el botón «Probar» (cualquier evento, por ejemplo
{}) y se BORRA. No es parte de la arquitectura ni queda expuesta en el API Gateway.

Es idempotente: cada ítem se escribe con attribute_not_exists(PK), así que ejecutarla dos veces no
pisa nada (devuelve cuántos ítems ya existían).

Datos mock (solo para pruebas; cámbialos o rota las claves antes de usar el sistema de verdad):
  cliente demo / local local_01 "MISE Centro"
  personas mock-dueno (código 1234), mock-admin (código 4321), mock-cajero, mock-garzon,
           mock-garzon2, mock-cocina
  impresoras imp_cocina, imp_barra, imp_caja con claves mock-clave-cocina, mock-clave-barra,
             mock-clave-caja
Si se define EMAIL_DUENO_REAL, además deja una invitación de dueño para ese email: al entrar con
Google por primera vez queda vinculado.

Manejador: lambda_function.lambda_handler · Capa: pos-dominio
Variables: TABLA_OPERACION, TABLA_CONFIGURACION, EMAIL_DUENO_REAL (opcional)
"""

import os

import boto3
from botocore.exceptions import ClientError

from pos_dominio import autorizacion, claves, tiempo
from pos_dominio.infra.dynamodb import a_item

TENANT, LOCAL = "demo", "local_01"
L = claves.local(TENANT, LOCAL)
CLAVES_IMPRESORAS = {"imp_cocina": "mock-clave-cocina", "imp_barra": "mock-clave-barra", "imp_caja": "mock-clave-caja"}
PERSONAS = [  # sub, nombre, rol, código de autorización
    ("mock-dueno", "Dueña Demo", "dueno", "1234"),
    ("mock-admin", "Admin Demo", "admin", "4321"),
    ("mock-cajero", "Cajero Demo", "cajero", None),
    ("mock-garzon", "Garzón Demo", "garzon", None),
    ("mock-garzon2", "Garzona Demo", "garzon", None),
    ("mock-cocina", "Cocina Demo", "cocina", None),
]
SECTORES = [("sector_salon", "Salón"), ("sector_terraza", "Terraza")]
MESAS = [(f"m{n:02d}", "sector_salon" if n <= 8 else "sector_terraza", n, 4 if n <= 8 else 2) for n in range(1, 13)]
CUARTOS = [("cocina", "Cocina", "imp_cocina"), ("barra", "Barra", "imp_barra")]
PRODUCTOS = [  # id, nombre, categoría, precio, cuarto, activo, modificadores
    ("empanada", "Empanada de pino", "Entradas", 2500, "cocina", True, []),
    ("ceviche", "Ceviche", "Entradas", 6900, "cocina", True, []),
    ("lomo", "Lomo a lo pobre", "Fondos", 12900, "cocina", True, [("a_punto", "A punto", 0), ("bien_cocido", "Bien cocido", 0)]),
    ("pizza", "Pizza napolitana", "Fondos", 9900, "cocina", True, [("xl", "Tamaño XL", 3000)]),
    ("pastel_choclo", "Pastel de choclo", "Fondos", 8500, "cocina", True, []),
    ("bebida", "Bebida", "Bebidas", 1800, "barra", True, []),
    ("pisco_sour", "Pisco sour", "Bebidas", 4500, "barra", True, []),
    ("cafe", "Café", "Bebidas", 1500, "barra", True, []),
    ("torta", "Torta de mil hojas", "Postres", 3900, "cocina", True, []),
    ("helado", "Helado artesanal", "Postres", 2900, "cocina", False, []),
]
MATERIAS = [("harina", "Harina", "kg", 25_000, 5_000), ("carne", "Carne de vacuno", "kg", 10_500, 3_000),
            ("pisco", "Pisco", "l", 6_000, 2_000)]


def items() -> list[tuple[str, dict]]:
    """(tabla, ítem). Hashes y sales se generan al ejecutar: ninguna clave queda en claro en la base."""
    cfg, ahora = claves.TABLA_CONFIGURACION, tiempo.iso(tiempo.ahora_utc())
    lista = [
        (cfg, {"PK": claves.tenant(TENANT), "SK": "TENANT", "tipo_item": "TENANT", "nombre": "Restaurantes Demo SpA",
               "estado": "activo", "version": 1}),
        (cfg, {"PK": L, "SK": claves.SK_LOCAL, "tipo_item": "LOCAL", "nombre_local": "MISE Centro", "marca": "MISE",
               "propina_sugerida_pct": 10, "umbral_diferencia_pb": 200, "umbral_diferencia_minimo": 5000,
               "impresora_caja_id": "imp_caja", "version": 1}),
        (cfg, {"PK": L, "SK": claves.SK_CATALOGO, "tipo_item": "CATALOGO", "version": 1}),
        (cfg, {"PK": L, "SK": "ESTACION#estacion_caja_01", "tipo_item": "ESTACION", "estacion_id": "estacion_caja_01",
               "nombre": "Caja principal", "tipo": "caja", "creada_en": ahora}),
    ]
    for sector_id, nombre in SECTORES:
        lista += [(cfg, {"PK": L, "SK": f"SECTOR#{sector_id}", "tipo_item": "SECTOR", "sector_id": sector_id,
                         "nombre": nombre, "activo": True, "version": 1}),
                  (cfg, {"PK": L, "SK": f"UNICO#SECTOR#{nombre.lower()}", "tipo_item": "UNICO", "ref_id": sector_id})]
    nombres_sector = dict(SECTORES)
    for mesa_id, sector_id, numero, capacidad in MESAS:
        lista += [(cfg, {"PK": L, "SK": claves.sk_mesa(mesa_id), "tipo_item": "MESA", "mesa_id": mesa_id,
                         "sector_id": sector_id, "sector_nombre": nombres_sector[sector_id], "numero": numero,
                         "capacidad": capacidad, "activa": True, "version": 1}),
                  (cfg, {"PK": L, "SK": f"UNICO#MESA#{sector_id}#{numero}", "tipo_item": "UNICO", "ref_id": mesa_id})]
    for impresora_id, clave in CLAVES_IMPRESORAS.items():
        hash_hex, sal_hex = autorizacion.hashear_clave_impresora(clave)
        lista.append((cfg, {"PK": L, "SK": claves.sk_impresora(impresora_id), "tipo_item": "IMPRESORA",
                            "impresora_id": impresora_id, "nombre": impresora_id.replace("imp_", "").capitalize(),
                            "modelo": "mock", "protocolo": "cloudprnt", "activa": True, "clave_hash": hash_hex,
                            "clave_sal": sal_hex, "clave_iter": 0, "version": 1}))
    for cuarto_id, nombre, impresora_id in CUARTOS:
        lista += [(cfg, {"PK": L, "SK": claves.sk_cuarto(cuarto_id), "tipo_item": "CUARTO", "cuarto_id": cuarto_id,
                         "nombre": nombre, "descripcion": "", "activo": True, "impresora_id": impresora_id, "version": 1}),
                  (cfg, {"PK": L, "SK": f"UNICO#CUARTO#{nombre.lower()}", "tipo_item": "UNICO", "ref_id": cuarto_id})]
    for producto_id, nombre, categoria, precio, cuarto_id, activo, modificadores in PRODUCTOS:
        lista.append((cfg, {"PK": L, "SK": claves.sk_producto(producto_id), "tipo_item": "PRODUCTO",
                            "producto_id": producto_id, "nombre": nombre, "categoria": categoria, "precio": precio,
                            "cuarto_id": cuarto_id, "activo": activo, "version": 1,
                            "modificadores": [{"modificador_id": m, "nombre": n, "precio_adicional": p}
                                              for m, n, p in modificadores]}))
    for mp_id, nombre, unidad, stock, minimo in MATERIAS:
        lista.append((cfg, {"PK": L, "SK": f"MP#{mp_id}", "tipo_item": "MATERIA_PRIMA", "materia_prima_id": mp_id,
                            "nombre": nombre, "unidad": unidad, "stock_actual_mil": stock, "stock_minimo_mil": minimo,
                            "activo": True, "version": 1}))
    lista.append((cfg, {"PK": L, "SK": "RECETA#pizza", "tipo_item": "RECETA", "producto_id": "pizza", "version": 1,
                        "ingredientes": [{"materia_prima_id": "harina", "cantidad_mil": 250}]}))
    for sub, nombre, rol, codigo in PERSONAS:
        email = f"{sub}@demo.invalid"
        membresia = {"PK": claves.usuario(sub), "SK": claves.sk_membresia(TENANT, LOCAL), "tipo_item": "MEMBRESIA",
                     "sub": sub, "tenant_id": TENANT, "local_id": LOCAL, "rol": rol, "nombre": nombre, "email": email,
                     "estado": "activo", "version": 1, "GSI1PK": claves.gsi_personal(L), "GSI1SK": f"{nombre}#{sub}"}
        if codigo:
            membresia["pin_hash"], membresia["pin_sal"], membresia["pin_iter"] = autorizacion.hashear(codigo)
        lista += [(cfg, {"PK": claves.usuario(sub), "SK": "PERFIL", "tipo_item": "PERFIL", "sub": sub, "email": email,
                         "nombre": nombre, "estado": "activo", "version": 1}),
                  (cfg, membresia),
                  (cfg, {"PK": claves.email(email), "SK": "SUB", "tipo_item": "EMAIL", "sub": sub, "email": email})]
    email_real = os.environ.get("EMAIL_DUENO_REAL", "").strip().lower()
    if email_real:
        lista.append((cfg, {"PK": claves.invitacion(email_real), "SK": claves.sk_membresia(TENANT, LOCAL),
                            "tipo_item": "INVITACION", "tenant_id": TENANT, "local_id": LOCAL, "rol": "dueno",
                            "nombre": "Dueño", "email": email_real, "estado": "invitado", "invitado_por": "semilla",
                            "GSI1PK": claves.gsi_personal(L), "GSI1SK": f"Dueño#INV#{email_real}"}))
    return lista


def sembrar(cliente, tablas: dict[str, str]) -> dict:
    creados = existentes = 0
    for tabla, item in items():
        try:
            cliente.put_item(TableName=tablas[tabla], Item=a_item(item), ConditionExpression="attribute_not_exists(PK)")
            creados += 1
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            existentes += 1
    return {"creados": creados, "ya_existian": existentes, "tenant_id": TENANT, "local_id": LOCAL}


def lambda_handler(_evento=None, _contexto=None) -> dict:
    tablas = {claves.TABLA_CONFIGURACION: os.environ["TABLA_CONFIGURACION"],
              claves.TABLA_OPERACION: os.environ["TABLA_OPERACION"]}
    return sembrar(boto3.client("dynamodb"), tablas)
