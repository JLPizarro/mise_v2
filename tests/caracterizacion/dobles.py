"""Repositorios en memoria que reproducen el SQL de mise-backend/app/infrastructure/repositories.

Cada método cita la sentencia SQL que imita. Los casos de uso congelados en legado/ los usan por
tipado de pato (no heredan de los ABC de ports.py, porque exigirían implementar métodos que las
pruebas no necesitan).
"""

from dataclasses import replace
from datetime import datetime, timezone
from itertools import count

from app.domain.entities import (
    ConfiguracionRestaurante,
    ItemComanda,
    Mesa,
    Modificador,
    Pago,
    Pedido,
    Producto,
    RetiroCaja,
    TurnoCaja,
    Usuario,
)

_secuencia = count(1)


def _id(prefijo: str) -> str:
    return f"{prefijo}_{next(_secuencia):06d}"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class MesasEnMemoria:
    def __init__(self):
        self.mesas: dict[str, Mesa] = {}

    def agregar(self, mesa_id: str, estado: str = "libre", garzon: str | None = None) -> Mesa:
        mesa = Mesa(mesa_id, "sector_1", "Salón", len(self.mesas) + 1, 4, estado, garzon, None)
        self.mesas[mesa_id] = mesa
        return mesa

    def find_by_id(self, mesa_id):
        return self.mesas.get(mesa_id)

    def ocupar_si_libre(self, mesa_id, garzon_id):
        # UPDATE mesas SET estado='ocupada', garzon_asignado_id=COALESCE(garzon_asignado_id, %s)
        # WHERE mesa_id=%s AND estado='libre'
        mesa = self.mesas.get(mesa_id)
        if mesa and mesa.estado == "libre":
            mesa.estado = "ocupada"
            mesa.garzon_asignado_id = mesa.garzon_asignado_id or garzon_id

    def marcar_precuenta(self, mesa_id):
        # UPDATE mesas SET estado='precuenta' WHERE mesa_id=%s  (sin condición de estado)
        mesa = self.mesas.get(mesa_id)
        if mesa is None:
            return None
        mesa.estado = "precuenta"
        return mesa

    def liberar(self, mesa_id):
        # UPDATE mesas SET estado='libre', garzon_asignado_id=NULL WHERE mesa_id=%s
        mesa = self.mesas.get(mesa_id)
        if mesa:
            mesa.estado = "libre"
            mesa.garzon_asignado_id = None


class ProductosEnMemoria:
    def __init__(self):
        self.productos: dict[str, Producto] = {}

    def agregar(self, producto_id, precio, activo=True, modificadores=()):
        mods = [Modificador(m_id, producto_id, nombre, recargo) for m_id, nombre, recargo in modificadores]
        producto = Producto(producto_id, f"Producto {producto_id}", "Fondos", precio, "cuarto_1", activo,
                            modificadores=mods)
        self.productos[producto_id] = producto
        return producto

    def find_by_id(self, producto_id):
        return self.productos.get(producto_id)

    def find_modificador(self, modificador_id, producto_id):
        # SELECT * FROM modificadores WHERE modificador_id=%s AND producto_id=%s
        producto = self.productos.get(producto_id)
        if producto is None:
            return None
        return next((m for m in producto.modificadores if m.modificador_id == modificador_id), None)


class PedidosEnMemoria:
    def __init__(self, productos: ProductosEnMemoria):
        self.pedidos: dict[str, Pedido] = {}
        self._productos = productos

    def _copia(self, pedido: Pedido) -> Pedido:
        # Cada lectura devuelve un objeto nuevo, como una consulta a Postgres.
        return replace(pedido, items=[replace(i) for i in pedido.items])

    def find_abierto_by_mesa(self, mesa_id):
        # WHERE mesa_id=%s AND estado IN ('abierto','precuenta') ORDER BY creado_en DESC LIMIT 1
        candidatos = [p for p in self.pedidos.values()
                      if p.mesa_id == mesa_id and p.estado in ("abierto", "precuenta")]
        return self._copia(candidatos[-1]) if candidatos else None

    def create(self, mesa_id, garzon_id):
        # INSERT INTO pedidos (mesa_id, garzon_id) -> estado DEFAULT 'abierto'
        pedido = Pedido(_id("ped"), mesa_id, garzon_id, "abierto", [])
        self.pedidos[pedido.pedido_id] = pedido
        return self._copia(pedido)

    def find_by_id(self, pedido_id):
        pedido = self.pedidos.get(pedido_id)
        return self._copia(pedido) if pedido else None

    def add_item(self, pedido_id, producto_id, modificador_id, cantidad, observacion_libre, precio_unitario):
        # INSERT INTO items_comanda (...) -> estado DEFAULT 'en_espera'
        producto = self._productos.find_by_id(producto_id)
        modificador = self._productos.find_modificador(modificador_id, producto_id) if modificador_id else None
        item = ItemComanda(_id("item"), pedido_id, producto_id, modificador_id, cantidad, "en_espera",
                           observacion_libre, precio_unitario, producto, modificador)
        self.pedidos[pedido_id].items.append(item)
        return replace(item)

    def update_item(self, pedido_id, item_id, cantidad=None, estado=None, observacion_libre=None,
                    set_observacion=False):
        # UPDATE items_comanda SET ... WHERE pedido_id=%s AND item_id=%s  (sin condición de estado)
        pedido = self.pedidos.get(pedido_id)
        item = next((i for i in pedido.items if i.item_id == item_id), None) if pedido else None
        if item is None:
            return None
        if cantidad is not None:
            item.cantidad = cantidad
        if estado is not None:
            item.estado = estado
        if set_observacion:
            item.observacion_libre = observacion_libre
        return replace(item)

    def delete_item_en_espera(self, pedido_id, item_id):
        # DELETE ... WHERE pedido_id=%s AND item_id=%s AND estado='en_espera'
        pedido = self.pedidos.get(pedido_id)
        if pedido is None:
            return False
        for item in pedido.items:
            if item.item_id == item_id and item.estado == "en_espera":
                pedido.items.remove(item)
                return True
        return False

    def enviar_tanda(self, pedido_id):
        # UPDATE items_comanda SET estado='enviado' WHERE pedido_id=%s AND estado='en_espera'
        for item in self.pedidos[pedido_id].items:
            if item.estado == "en_espera":
                item.estado = "enviado"
        return [replace(i) for i in self.pedidos[pedido_id].items]

    def marcar_precuenta(self, pedido_id):
        # UPDATE pedidos SET estado='precuenta' WHERE pedido_id=%s  (sin condición de estado)
        pedido = self.pedidos.get(pedido_id)
        if pedido is None:
            return None
        pedido.estado = "precuenta"
        return self._copia(pedido)

    def cerrar(self, pedido_id):
        self.pedidos[pedido_id].estado = "cerrado"


class PagosEnMemoria:
    def __init__(self):
        self.pagos: list[Pago] = []

    def create(self, pedido_id, mesa_id, turno_id, metodo, monto, propina, codigo_autorizacion_pos,
               efectivo_recibido, vuelto, rut_facturacion, razon_social_facturacion, tipo_division,
               tipo_documento, items_cobrados):
        pago = Pago(_id("pago"), pedido_id, mesa_id, metodo, monto, propina, codigo_autorizacion_pos,
                    efectivo_recibido, vuelto, _ahora(), turno_id, rut_facturacion,
                    razon_social_facturacion, tipo_division, tipo_documento, list(items_cobrados))
        self.pagos.append(pago)
        return pago

    def list_by_pedido(self, pedido_id):
        return [p for p in self.pagos if p.pedido_id == pedido_id]

    def list_by_turno(self, turno_id):
        return [p for p in self.pagos if p.turno_id == turno_id]


class TurnosEnMemoria:
    def __init__(self):
        self.turnos: dict[str, TurnoCaja] = {}

    def find_abierto(self):
        return next((replace(t) for t in self.turnos.values() if t.estado == "abierto"), None)

    def find_by_id(self, turno_id):
        turno = self.turnos.get(turno_id)
        return replace(turno) if turno else None

    def abrir(self, usuario_id, monto_apertura):
        turno = TurnoCaja(_id("turno"), usuario_id, monto_apertura, _ahora(), "abierto", None, None, False,
                          None, None, None, None, None)
        self.turnos[turno.turno_id] = turno
        return replace(turno)

    def registrar_conteo(self, turno_id, monto, es_segundo_conteo):
        turno = self.turnos[turno_id]
        if es_segundo_conteo:
            turno.segundo_conteo = monto
        else:
            turno.primer_conteo = monto
        return replace(turno)

    def marcar_requiere_segundo_conteo(self, turno_id):
        self.turnos[turno_id].requiere_segundo_conteo = True

    def registrar_conciliacion_terminal(self, turno_id, total_debito_pos, total_credito_pos,
                                        total_notas_credito_pos):
        turno = self.turnos[turno_id]
        turno.total_debito_pos = total_debito_pos
        turno.total_credito_pos = total_credito_pos
        turno.total_notas_credito_pos = total_notas_credito_pos
        return replace(turno)

    def cerrar(self, turno_id, usuario_cierre_id):
        turno = self.turnos[turno_id]
        turno.estado = "cerrado"
        turno.usuario_cierre_id = usuario_cierre_id
        turno.cerrado_en = _ahora()
        return replace(turno)


class RetirosEnMemoria:
    def __init__(self):
        self.retiros: list[RetiroCaja] = []

    def create(self, turno_id, usuario_id, autorizado_por, monto, motivo):
        retiro = RetiroCaja(_id("retiro"), turno_id, usuario_id, autorizado_por, monto, motivo, _ahora())
        self.retiros.append(retiro)
        return retiro

    def list_by_turno(self, turno_id):
        return [r for r in self.retiros if r.turno_id == turno_id]


class ConfiguracionEnMemoria:
    def __init__(self, umbral_pct: float = 2.0, umbral_minimo: int = 5000):
        self.config = ConfiguracionRestaurante("Local", "Marca", 10, umbral_pct, umbral_minimo)

    def obtener(self):
        return self.config


class UsuariosEnMemoria:
    """find_autorizador_por_pin recorre los dueños y admins activos con PIN y devuelve el primero
    que calza (usuario_repository.py). Aquí el PIN se guarda en claro: el hash no cambia el orden
    ni el resultado de la búsqueda."""

    def __init__(self):
        self.usuarios: list[tuple[Usuario, str | None]] = []

    def agregar(self, usuario_id, rol, pin=None, activo=True):
        self.usuarios.append((Usuario(usuario_id, usuario_id, f"{usuario_id}@x.cl", rol, activo), pin))

    def find_autorizador_por_pin(self, pin):
        for usuario, pin_guardado in self.usuarios:
            if usuario.rol in ("dueno", "admin") and usuario.activo and pin_guardado is not None \
                    and pin_guardado == pin:
                return usuario
        return None
