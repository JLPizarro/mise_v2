"""Puertos (interfaces) que la capa de aplicación necesita. Implementados por adaptadores
en infrastructure/repositories — así los casos de uso no dependen de Postgres ni de ningún
detalle de persistencia."""

from abc import ABC, abstractmethod

from app.domain.entities import (
    Usuario,
    Sector,
    Mesa,
    Producto,
    Modificador,
    Pedido,
    ItemComanda,
    ItemCobrado,
    Pago,
    TurnoCaja,
    RetiroCaja,
    CuartoCocina,
    MateriaPrima,
    Receta,
    IngredienteReceta,
    ConfiguracionRestaurante,
    EventoSalida,
    NodoCloud,
)


class UsuarioRepository(ABC):
    @abstractmethod
    def find_by_email(self, email: str) -> Usuario | None: ...

    @abstractmethod
    def find_by_id(self, usuario_id: str) -> Usuario | None: ...

    @abstractmethod
    def create(
        self,
        nombre: str,
        email: str,
        proveedor: str | None,
        rol: str = "garzon",
    ) -> Usuario: ...

    @abstractmethod
    def list_all(self) -> list[Usuario]: ...

    @abstractmethod
    def set_pin_hash(self, usuario_id: str, pin_hash: str) -> None: ...

    @abstractmethod
    def find_autorizador_por_pin(self, pin: str) -> Usuario | None:
        """Busca, entre los admin/dueño con PIN configurado, cuál coincide
        con el PIN entregado. Verifica el hash dentro del repositorio para
        que el hash almacenado nunca salga de la capa de infraestructura."""
        ...

    @abstractmethod
    def update(
        self,
        usuario_id: str,
        nombre: str | None = None,
        rol: str | None = None,
        activo: bool | None = None,
    ) -> Usuario | None: ...

    @abstractmethod
    def tiene_historial(self, usuario_id: str) -> bool:
        """True si el usuario aparece en pedidos/pagos/mesas/turnos/retiros —
        en ese caso no se puede borrar de verdad, solo desactivar."""
        ...

    @abstractmethod
    def delete(self, usuario_id: str) -> bool: ...


class SectorRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[Sector]: ...

    @abstractmethod
    def find_by_id(self, sector_id: str) -> Sector | None: ...

    @abstractmethod
    def create(self, nombre: str, activo: bool = True) -> Sector: ...

    @abstractmethod
    def update(
        self,
        sector_id: str,
        nombre: str | None = None,
        activo: bool | None = None,
    ) -> Sector | None: ...


class MesaRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[Mesa]: ...

    @abstractmethod
    def find_by_id(self, mesa_id: str) -> Mesa | None: ...

    @abstractmethod
    def create(
        self, sector_id: str, numero: int, capacidad: int
    ) -> Mesa: ...

    @abstractmethod
    def update(
        self,
        mesa_id: str,
        estado: str | None = None,
        garzon_asignado_id: str | None = None,
        reserva_id: str | None = None,
        set_garzon: bool = False,
        set_reserva: bool = False,
        numero: int | None = None,
        capacidad: int | None = None,
        sector_id: str | None = None,
    ) -> Mesa | None: ...

    @abstractmethod
    def ocupar_si_libre(self, mesa_id: str, garzon_id: str) -> None: ...

    @abstractmethod
    def marcar_precuenta(self, mesa_id: str) -> Mesa | None: ...

    @abstractmethod
    def liberar(self, mesa_id: str) -> None: ...


class ProductoRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[Producto]: ...

    @abstractmethod
    def find_by_id(self, producto_id: str) -> Producto | None: ...

    @abstractmethod
    def find_modificador(
        self, modificador_id: str, producto_id: str
    ) -> Modificador | None: ...

    @abstractmethod
    def create(
        self,
        nombre: str,
        categoria: str,
        precio: int,
        cuarto_cocina_id: str,
        activo: bool,
        descripcion: str | None,
        modificadores: list[tuple[str, int]],
    ) -> Producto: ...

    @abstractmethod
    def update(
        self,
        producto_id: str,
        nombre: str | None = None,
        categoria: str | None = None,
        precio: int | None = None,
        cuarto_cocina_id: str | None = None,
        activo: bool | None = None,
        descripcion: str | None = None,
        set_descripcion: bool = False,
        modificadores: list[tuple[str, int]] | None = None,
    ) -> Producto | None:
        """Si `modificadores` no es None, reemplaza la lista completa de
        modificadores del producto (igual que el formulario del dashboard,
        que siempre entrega el set completo, no un delta)."""
        ...


class CuartoCocinaRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[CuartoCocina]: ...

    @abstractmethod
    def find_by_id(self, cuarto_cocina_id: str) -> CuartoCocina | None: ...

    @abstractmethod
    def create(self, cuarto: CuartoCocina) -> CuartoCocina: ...

    @abstractmethod
    def update(self, cuarto: CuartoCocina) -> CuartoCocina | None: ...


class MateriaPrimaRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[MateriaPrima]: ...

    @abstractmethod
    def find_by_id(self, materia_prima_id: str) -> MateriaPrima | None: ...

    @abstractmethod
    def create(
        self,
        nombre: str,
        unidad_medida: str,
        stock_actual: float,
        stock_minimo: float,
        activo: bool,
    ) -> MateriaPrima: ...

    @abstractmethod
    def update(
        self,
        materia_prima_id: str,
        nombre: str | None = None,
        unidad_medida: str | None = None,
        stock_actual: float | None = None,
        stock_minimo: float | None = None,
        activo: bool | None = None,
    ) -> MateriaPrima | None: ...


class RecetaRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[Receta]: ...

    @abstractmethod
    def find_by_producto(self, producto_id: str) -> Receta | None: ...

    @abstractmethod
    def upsert(
        self, producto_id: str, ingredientes: list[IngredienteReceta]
    ) -> Receta:
        """Crea la receta del producto si no existe, o reemplaza su lista
        completa de ingredientes si ya existía."""
        ...


class ConfiguracionRepository(ABC):
    @abstractmethod
    def obtener(self) -> ConfiguracionRestaurante: ...

    @abstractmethod
    def actualizar(
        self,
        nombre_local: str | None = None,
        marca: str | None = None,
        propina_sugerida_pct: int | None = None,
        umbral_diferencia_pct: float | None = None,
        umbral_diferencia_minimo: int | None = None,
    ) -> ConfiguracionRestaurante: ...


class PedidoRepository(ABC):
    @abstractmethod
    def find_abierto_by_mesa(self, mesa_id: str) -> Pedido | None: ...

    @abstractmethod
    def create(self, mesa_id: str, garzon_id: str) -> Pedido: ...

    @abstractmethod
    def find_by_id(self, pedido_id: str) -> Pedido | None: ...

    @abstractmethod
    def list_by_filters(
        self, mesa_id: str | None = None, estado: str | None = None
    ) -> list[Pedido]: ...

    @abstractmethod
    def add_item(
        self,
        pedido_id: str,
        producto_id: str,
        modificador_id: str | None,
        cantidad: int,
        observacion_libre: str | None,
        precio_unitario: int,
    ) -> ItemComanda: ...

    @abstractmethod
    def update_item(
        self,
        pedido_id: str,
        item_id: str,
        cantidad: int | None = None,
        estado: str | None = None,
        observacion_libre: str | None = None,
        set_observacion: bool = False,
    ) -> ItemComanda | None: ...

    @abstractmethod
    def delete_item_en_espera(self, pedido_id: str, item_id: str) -> bool: ...

    @abstractmethod
    def enviar_tanda(self, pedido_id: str) -> list[ItemComanda]: ...

    @abstractmethod
    def marcar_precuenta(self, pedido_id: str) -> Pedido | None: ...

    @abstractmethod
    def cerrar(self, pedido_id: str) -> None: ...


class PagoRepository(ABC):
    @abstractmethod
    def create(
        self,
        pedido_id: str | None,
        mesa_id: str,
        turno_id: str | None,
        metodo: str,
        monto: int,
        propina: int,
        codigo_autorizacion_pos: str | None,
        efectivo_recibido: int | None,
        vuelto: int | None,
        rut_facturacion: str | None,
        razon_social_facturacion: str | None,
        tipo_division: str | None,
        tipo_documento: str | None,
        items_cobrados: list[ItemCobrado],
    ) -> Pago: ...

    @abstractmethod
    def list_by_mesa(self, mesa_id: str) -> list[Pago]: ...

    @abstractmethod
    def list_by_pedido(self, pedido_id: str) -> list[Pago]: ...

    @abstractmethod
    def list_by_turno(self, turno_id: str) -> list[Pago]: ...


class TurnoCajaRepository(ABC):
    @abstractmethod
    def find_abierto(self) -> TurnoCaja | None: ...

    @abstractmethod
    def find_by_id(self, turno_id: str) -> TurnoCaja | None: ...

    @abstractmethod
    def abrir(self, usuario_id: str, monto_apertura: int) -> TurnoCaja: ...

    @abstractmethod
    def registrar_conteo(
        self, turno_id: str, monto: int, es_segundo_conteo: bool
    ) -> TurnoCaja: ...

    @abstractmethod
    def marcar_requiere_segundo_conteo(self, turno_id: str) -> None: ...

    @abstractmethod
    def registrar_conciliacion_terminal(
        self,
        turno_id: str,
        total_debito_pos: int,
        total_credito_pos: int,
        total_notas_credito_pos: int,
    ) -> TurnoCaja: ...

    @abstractmethod
    def cerrar(self, turno_id: str, usuario_cierre_id: str) -> TurnoCaja: ...


class RetiroCajaRepository(ABC):
    @abstractmethod
    def create(
        self,
        turno_id: str,
        usuario_id: str,
        autorizado_por: str,
        monto: int,
        motivo: str,
    ) -> RetiroCaja: ...

    @abstractmethod
    def list_by_turno(self, turno_id: str) -> list[RetiroCaja]: ...


class EventoSalidaRepository(ABC):
    """Outbox de eventos pendientes de subir a la nube (ver EventoSalida)."""

    @abstractmethod
    def list_pendientes(self, limite: int) -> list[EventoSalida]: ...

    @abstractmethod
    def marcar_enviados(self, ulids: list[str]) -> None: ...

    @abstractmethod
    def contar_pendientes(self) -> int: ...


class NodoCloudRepository(ABC):
    """Identidad y estado de sincronización de este local frente a la nube."""

    @abstractmethod
    def obtener(self) -> NodoCloud: ...

    @abstractmethod
    def guardar_identidad(
        self,
        tenant_id: str,
        local_id: str,
        clave_privada_pem: str,
        clave_publica_pem: str,
    ) -> NodoCloud: ...

    @abstractmethod
    def registrar_sync(self, ok: bool, error: str | None = None) -> None: ...
