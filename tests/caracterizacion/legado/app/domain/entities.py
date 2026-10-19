"""Entidades del dominio de MISE. Sin dependencias de FastAPI ni de la base de datos."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Usuario:
    usuario_id: str
    nombre: str
    email: str
    rol: str
    activo: bool


@dataclass
class Sector:
    sector_id: str
    nombre: str
    activo: bool = True


@dataclass
class Mesa:
    mesa_id: str
    sector_id: str
    sector_nombre: str
    numero: int
    capacidad: int
    estado: str
    garzon_asignado_id: str | None
    reserva_id: str | None


@dataclass
class Modificador:
    modificador_id: str
    producto_id: str
    nombre: str
    precio_adicional: int


@dataclass
class Producto:
    producto_id: str
    nombre: str
    categoria: str
    precio: int
    cuarto_cocina_id: str
    activo: bool
    descripcion: str | None = None
    imagen_url: str | None = None
    modificadores: list[Modificador] = field(default_factory=list)


@dataclass
class ItemComanda:
    item_id: str
    pedido_id: str
    producto_id: str
    modificador_id: str | None
    cantidad: int
    estado: str
    observacion_libre: str | None
    precio_unitario: int
    producto: Producto | None = None
    modificador: Modificador | None = None


@dataclass
class Pedido:
    pedido_id: str
    mesa_id: str
    garzon_id: str
    estado: str
    items: list[ItemComanda] = field(default_factory=list)


@dataclass
class ItemCobrado:
    item_id: str
    cantidad: int


@dataclass
class Pago:
    pago_id: str
    pedido_id: str | None
    mesa_id: str
    metodo: str
    monto: int
    propina: int
    codigo_autorizacion_pos: str | None
    efectivo_recibido: int | None
    vuelto: int | None
    fecha: datetime
    turno_id: str | None = None
    rut_facturacion: str | None = None
    razon_social_facturacion: str | None = None
    tipo_division: str | None = None
    tipo_documento: str | None = None
    items_cobrados: list[ItemCobrado] = field(default_factory=list)


@dataclass
class TurnoCaja:
    turno_id: str
    usuario_apertura_id: str
    monto_apertura: int
    abierto_en: datetime
    estado: str
    primer_conteo: int | None
    segundo_conteo: int | None
    requiere_segundo_conteo: bool
    total_debito_pos: int | None
    total_credito_pos: int | None
    total_notas_credito_pos: int | None
    usuario_cierre_id: str | None
    cerrado_en: datetime | None


@dataclass
class RetiroCaja:
    retiro_id: str
    turno_id: str
    usuario_id: str
    autorizado_por: str
    monto: int
    motivo: str
    creado_en: datetime


@dataclass
class Impresora:
    nombre: str
    direccion: str
    puerto: int
    activa: bool


@dataclass
class CuartoCocina:
    cuarto_cocina_id: str
    nombre: str
    descripcion: str
    activo: bool
    impresora: Impresora | None = None


@dataclass
class MateriaPrima:
    materia_prima_id: str
    nombre: str
    unidad_medida: str
    stock_actual: float
    stock_minimo: float
    activo: bool


@dataclass
class IngredienteReceta:
    materia_prima_id: str
    cantidad: float


@dataclass
class Receta:
    receta_id: str
    producto_id: str
    ingredientes: list[IngredienteReceta] = field(default_factory=list)


@dataclass
class ConfiguracionRestaurante:
    nombre_local: str
    marca: str
    propina_sugerida_pct: int
    umbral_diferencia_pct: float
    umbral_diferencia_minimo: int


@dataclass
class EventoSalida:
    """Fila del outbox: un hecho local (ej. un pago) pendiente de subir a
    la nube. Desacopla el registro del pago de la disponibilidad de la
    nube — el restaurante sigue cobrando aunque no haya internet."""

    id: int
    ulid: str
    tipo_evento: str
    payload: dict
    creado_en: datetime
    enviado_en: datetime | None = None


@dataclass
class NodoCloud:
    """Identidad de este local frente a la nube (fleet de AWS). Vacía
    hasta que un dueño/admin enrola el nodo desde el panel."""

    tenant_id: str | None = None
    local_id: str | None = None
    clave_privada_pem: str | None = None
    clave_publica_pem: str | None = None
    enrolado_en: datetime | None = None
    ultimo_sync_en: datetime | None = None
    ultimo_error: str | None = None

    @property
    def enrolado(self) -> bool:
        return bool(
            self.tenant_id and self.local_id and self.clave_privada_pem
        )
