"""Datos mínimos de un local para las pruebas de integración (mismo formato que la semilla de la guía)."""

from pos_dominio import autorizacion, claves, ids
from pos_dominio.contexto import Contexto
from pos_dominio.infra.dynamodb import a_item

TENANT, LOCAL = "demo", "local_01"
L = claves.local(TENANT, LOCAL)
CODIGO_ADMIN = "4321"
ITERACIONES_PRUEBA = 1_000  # bajas para que las pruebas sean rápidas; en producción, 200.000


def _poner(dynamo, tabla, pk, sk, atributos):
    dynamo.put_item(TableName=tabla, Item=a_item({"PK": pk, "SK": sk, **atributos}))


def sembrar(dynamo) -> None:
    cfg = "configuracion"
    _poner(dynamo, cfg, L, claves.SK_LOCAL, {"tipo_item": "LOCAL", "nombre_local": "Local Demo", "marca": "MISE",
                                            "propina_sugerida_pct": 10, "umbral_diferencia_pb": 200,
                                            "umbral_diferencia_minimo": 5000, "impresora_caja_id": "imp_caja",
                                            "version": 1})
    for mesa_id, numero in (("m1", 1), ("m2", 2), ("m3", 3)):
        _poner(dynamo, cfg, L, claves.sk_mesa(mesa_id), {"tipo_item": "MESA", "mesa_id": mesa_id, "sector_id": "s1",
                                                        "sector_nombre": "Salón", "numero": numero, "capacidad": 4,
                                                        "activa": True, "version": 1})
    _poner(dynamo, cfg, L, claves.sk_producto("pizza"), {
        "tipo_item": "PRODUCTO", "producto_id": "pizza", "nombre": "Pizza", "categoria": "Fondos", "precio": 8000,
        "cuarto_id": "cocina", "activo": True, "version": 1,
        "modificadores": [{"modificador_id": "xl", "nombre": "XL", "precio_adicional": 2000}]})
    _poner(dynamo, cfg, L, claves.sk_producto("bebida"), {
        "tipo_item": "PRODUCTO", "producto_id": "bebida", "nombre": "Bebida", "categoria": "Bebidas", "precio": 1500,
        "cuarto_id": "barra", "activo": True, "version": 1, "modificadores": []})
    _poner(dynamo, cfg, L, claves.sk_producto("agotado"), {
        "tipo_item": "PRODUCTO", "producto_id": "agotado", "nombre": "Agotado", "categoria": "Postres", "precio": 3000,
        "cuarto_id": "cocina", "activo": False, "version": 1, "modificadores": []})
    _poner(dynamo, cfg, L, claves.sk_cuarto("cocina"), {"tipo_item": "CUARTO", "cuarto_id": "cocina",
                                                        "nombre": "Cocina", "activo": True, "impresora_id": "imp_cocina",
                                                        "version": 1})
    _poner(dynamo, cfg, L, claves.sk_cuarto("barra"), {"tipo_item": "CUARTO", "cuarto_id": "barra", "nombre": "Barra",
                                                       "activo": True, "version": 1})
    _poner(dynamo, cfg, L, claves.sk_impresora("imp_cocina"), {"tipo_item": "IMPRESORA", "impresora_id": "imp_cocina",
                                                                "nombre": "Cocina", "activa": True, "version": 1})
    hash_hex, sal_hex, iteraciones = autorizacion.hashear(CODIGO_ADMIN, iteraciones=ITERACIONES_PRUEBA)
    for sub, rol in (("dueno1", "dueno"), ("admin1", "admin"), ("cajero1", "cajero"), ("garzon1", "garzon"),
                     ("cocina1", "cocina")):
        pin = {"pin_hash": hash_hex, "pin_sal": sal_hex, "pin_iter": iteraciones} if rol in ("dueno", "admin") else {}
        # Sin PERFIL la identidad rechaza a la persona (USUARIO_NO_REGISTRADO), aunque tenga membresías.
        _poner(dynamo, cfg, claves.usuario(sub), "PERFIL", {"tipo_item": "PERFIL", "sub": sub, "email": f"{sub}@demo.cl",
                                                             "nombre": sub.capitalize(), "estado": "activo", "version": 1})
        _poner(dynamo, cfg, claves.email(f"{sub}@demo.cl"), "SUB", {"tipo_item": "EMAIL", "sub": sub,
                                                                     "email": f"{sub}@demo.cl"})
        _poner(dynamo, cfg, claves.usuario(sub), claves.sk_membresia(TENANT, LOCAL), {
            "tipo_item": "MEMBRESIA", "sub": sub, "tenant_id": TENANT, "local_id": LOCAL, "rol": rol,
            "nombre": sub.capitalize(), "email": f"{sub}@demo.cl", "estado": "activo", "version": 1, **pin,
            "GSI1PK": claves.gsi_personal(L), "GSI1SK": f"{sub}#{sub}"})


def ctx(usuario: str = "garzon1", rol: str = "garzon", command_id: str | None = None, **extra) -> Contexto:
    return Contexto(tenant_id=TENANT, local_id=LOCAL, usuario_id=usuario, rol=rol,
                    command_id=command_id or ids.nuevo_ulid(), usuario_nombre=usuario.capitalize(), **extra)


def contar(dynamo, tabla: str, pk: str, prefijo: str = "") -> int:
    from pos_dominio.infra.dynamodb import AlmacenDynamo

    return len(AlmacenDynamo(dynamo).consultar(tabla, pk, prefijo=prefijo or None))
