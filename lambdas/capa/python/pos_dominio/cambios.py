"""Lo que una operación decide escribir, descrito sin boto3.

El dominio devuelve un `Resultado` con `cambios` y `eventos`. El adaptador de DynamoDB los traduce
a una sola TransactWriteItems, agregando el ítem CMD al inicio y los EVT al final (patrón outbox).

Concurrencia: toda entidad mutable lleva `version`. `Guardar` reemplaza el ítem completo con la
condición `version = leída` (o `attribute_not_exists(PK)` si se está creando). Las reglas de estado
se validan en el dominio sobre una lectura consistente; la versión garantiza que nadie cambió el
ítem entre la lectura y la escritura. Si cambió, el ejecutor relee y decide de nuevo una vez.
"""

from dataclasses import dataclass, field

from pos_dominio.errores import ErrorDominio

# --- Condiciones (árbol pequeño que el adaptador compila a ConditionExpression) ------------------


def igual(atributo: str, valor):
    return ("=", atributo, valor)


def distinto(atributo: str, valor):
    return ("<>", atributo, valor)


def en(atributo: str, valores):
    return ("in", atributo, tuple(valores))


def existe(atributo: str = "PK"):
    return ("existe", atributo)


def no_existe(atributo: str = "PK"):
    return ("no_existe", atributo)


def y(*condiciones):
    return ("y", tuple(c for c in condiciones if c is not None))


def o(*condiciones):
    return ("o", tuple(c for c in condiciones if c is not None))


# --- Cambios ---------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Cambio:
    tabla: str
    pk: str
    sk: str
    # Error de negocio a informar si la condición de este cambio falla. None = conflicto genérico.
    al_fallar: ErrorDominio | None = None
    # True = si la condición falla, releer y volver a decidir (una vez) en vez de rechazar.
    reintentar: bool = False


@dataclass(kw_only=True)
class Guardar(Cambio):
    """Reemplaza el ítem completo. version_leida = 0 significa que el ítem no existe todavía.

    El adaptador escribe `version = version_leida + 1`."""

    atributos: dict
    version_leida: int
    condicion_extra: tuple | None = None
    reintentar: bool = True


@dataclass(kw_only=True)
class Crear(Cambio):
    """Inserta un ítem nuevo con attribute_not_exists(PK)."""

    atributos: dict


@dataclass(kw_only=True)
class Reemplazar(Cambio):
    """Reemplaza un ítem que debe existir (attribute_exists(PK)).

    Para ítems sin versión propia, como las líneas de un pedido: los protege la versión del ítem
    PEDIDO, que va en la misma transacción."""

    atributos: dict


@dataclass(kw_only=True)
class Sumar(Cambio):
    """UpdateItem con ADD sobre contadores (y SET opcional). Sube `version` en 1."""

    incrementos: dict
    asignar: dict = field(default_factory=dict)
    condicion: tuple | None = None


@dataclass(kw_only=True)
class Borrar(Cambio):
    condicion: tuple | None = None


# --- Resultado ----------------------------------------------------------------------------------


@dataclass
class Evento:
    tipo: str
    datos: dict


@dataclass
class Resultado:
    respuesta: dict
    http: int = 200
    cambios: list = field(default_factory=list)
    eventos: list = field(default_factory=list)

    @property
    def sin_escritura(self) -> bool:
        return not self.cambios and not self.eventos


@dataclass
class Rechazo:
    """Un rechazo de negocio que igual debe escribir algo (por ejemplo, contar un código fallido).

    Se guarda el comando como `rechazado` junto con los cambios en la misma transacción."""

    error: ErrorDominio
    cambios: list = field(default_factory=list)
    eventos: list = field(default_factory=list)
