"""Entidades del dominio como dataclasses. Reemplazan a las entidades y esquemas Pydantic del local.

`a_atributos()` produce los atributos que se guardan (sin claves ni campos vacíos) y
`desde_atributos()` reconstruye la entidad ignorando atributos de infraestructura (PK, SK, GSI...).
Los montos son siempre int.
"""

from dataclasses import asdict, dataclass, field, fields

ESTADOS_MESA = ("libre", "ocupada", "precuenta", "bloqueada")
ESTADOS_PEDIDO = ("abierto", "precuenta", "cerrado")
ESTADOS_ITEM = ("en_espera", "enviado")
METODOS_PAGO = ("efectivo", "debito", "credito", "transferencia")
TIPOS_DIVISION = ("completa", "items", "partes_iguales", "monto_libre")
TIPOS_DOCUMENTO = ("boleta", "factura")
ROLES = ("dueno", "admin", "cajero", "garzon", "cocina")


class _Entidad:
    _excluir: tuple = ()

    def a_atributos(self) -> dict:
        datos = asdict(self)
        for nombre in self._excluir:
            datos.pop(nombre, None)
        return {k: v for k, v in datos.items() if v is not None}

    @classmethod
    def desde_atributos(cls, datos: dict):
        nombres = {f.name for f in fields(cls)} - set(cls._excluir)
        return cls(**{k: v for k, v in datos.items() if k in nombres})


@dataclass
class Modificador(_Entidad):
    modificador_id: str
    nombre: str
    precio_adicional: int = 0


@dataclass
class Producto(_Entidad):
    producto_id: str
    nombre: str
    categoria: str
    precio: int
    cuarto_id: str
    activo: bool = True
    descripcion: str | None = None
    modificadores: list = field(default_factory=list)
    version: int = 0

    @classmethod
    def desde_atributos(cls, datos: dict):
        producto = super().desde_atributos(datos)
        producto.modificadores = [m if isinstance(m, Modificador) else Modificador.desde_atributos(m)
                                  for m in producto.modificadores]
        return producto

    def modificador(self, modificador_id: str) -> Modificador | None:
        return next((m for m in self.modificadores if m.modificador_id == modificador_id), None)


@dataclass
class MesaEstructura(_Entidad):
    mesa_id: str
    sector_id: str
    sector_nombre: str
    numero: int
    capacidad: int
    activa: bool = True
    version: int = 0


@dataclass
class MesaEstado(_Entidad):
    mesa_id: str
    estado: str = "libre"
    pedido_id: str | None = None
    garzon_id: str | None = None
    version: int = 0


@dataclass
class Item(_Entidad):
    item_id: str
    producto_id: str
    nombre: str
    categoria: str
    cuarto_id: str
    cantidad: int
    precio_unitario: int
    creado_en: str
    estado: str = "en_espera"
    modificador_id: str | None = None
    modificador_nombre: str | None = None
    observacion: str | None = None
    cobrado: int = 0
    tanda: int | None = None
    enviado_en: str | None = None

    @property
    def subtotal(self) -> int:
        return self.precio_unitario * self.cantidad

    @property
    def sin_cobrar(self) -> int:
        return self.cantidad - self.cobrado


@dataclass
class Pago(_Entidad):
    pago_id: str
    turno_id: str
    metodo: str
    monto: int
    propina: int
    tipo_division: str
    usuario_id: str
    fecha: str
    codigo_autorizacion_pos: str | None = None
    efectivo_recibido: int | None = None
    vuelto: int | None = None
    items_cobrados: list = field(default_factory=list)


@dataclass
class Pedido(_Entidad):
    _excluir = ("items", "pagos")

    pedido_id: str
    mesa_id: str
    garzon_id: str
    creado_en: str
    estado: str = "abierto"
    total: int = 0
    pagado: int = 0
    propina_total: int = 0
    n_items: int = 0
    n_tandas: int = 0
    cerrado_en: str | None = None
    documento: dict | None = None
    turno_cierre_id: str | None = None
    origen: str = "normal"
    version: int = 0
    items: list = field(default_factory=list)
    pagos: list = field(default_factory=list)

    @property
    def saldo(self) -> int:
        return self.total - self.pagado

    def item(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.item_id == item_id), None)


@dataclass
class Turno(_Entidad):
    turno_id: str
    usuario_apertura_id: str
    monto_apertura: int
    abierto_en: str
    fecha_operativa: str
    estado: str = "abierto"
    primer_conteo: int | None = None
    segundo_conteo: int | None = None
    requiere_segundo_conteo: bool = False
    conciliacion: dict | None = None
    tot_efectivo: int = 0
    tot_debito: int = 0
    tot_credito: int = 0
    tot_transferencia: int = 0
    tot_retiros: int = 0
    n_pagos: int = 0
    n_ventas: int = 0
    tot_ventas: int = 0
    resultado: dict | None = None
    usuario_cierre_id: str | None = None
    cerrado_en: str | None = None
    version: int = 0

    @property
    def efectivo_esperado(self) -> int:
        # caja_use_cases: apertura + Σ(monto + propina) en efectivo − Σ retiros
        return self.monto_apertura + self.tot_efectivo - self.tot_retiros


@dataclass
class ConfigLocal(_Entidad):
    nombre_local: str
    marca: str
    propina_sugerida_pct: int = 10
    umbral_diferencia_pb: int = 200
    umbral_diferencia_minimo: int = 5000
    impresora_caja_id: str | None = None
    version: int = 0


@dataclass
class Cuarto(_Entidad):
    cuarto_id: str
    nombre: str
    activo: bool = True
    impresora_id: str | None = None
    descripcion: str = ""
    version: int = 0


@dataclass
class Impresora(_Entidad):
    impresora_id: str
    nombre: str
    activa: bool = True
    modelo: str = ""
    protocolo: str = "cloudprnt"
    clave_hash: str | None = None
    clave_sal: str | None = None
    clave_iter: int | None = None
    version: int = 0


@dataclass
class Membresia(_Entidad):
    sub: str
    tenant_id: str
    local_id: str
    rol: str
    nombre: str
    email: str
    estado: str = "activo"
    pin_hash: str | None = None
    pin_sal: str | None = None
    pin_iter: int | None = None
    version: int = 0

    @property
    def activa(self) -> bool:
        return self.estado == "activo"


@dataclass
class Bloqueo(_Entidad):
    intentos: int = 0
    ventana_hasta: int = 0
    bloqueado_hasta: int = 0
    version: int = 0
