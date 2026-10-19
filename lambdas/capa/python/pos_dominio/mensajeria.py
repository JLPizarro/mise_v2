"""Catálogo central de la mensajería: canales, rutas de eventos, avisos y reglas de los destinos.

Es el único lugar donde se declara:
- qué canales existen (flujo de eventos, colas, colas de fallidos, temas y la regla programada),
  quién produce y quién consume en cada uno y cómo se tratan sus fallos;
- qué evento llega a qué canal y a qué consumidor (rutas);
- qué avisos existen, a qué tema van y cuáles puede recibir un destino administrable;
- cómo se valida una solicitud para crear destinos o reglas.

Lo usan `procesador-eventos` y `tareas-programadas` (a qué tema publicar cada aviso), la función
`mensajeria` (validar y armar las reglas de distribución), `infra/cloudshell/desplegar.sh` (crea las
colas desde aquí con `ayudante.py canales`) y las pruebas, que comprueban que la documentación y el
despliegue no se desvían de este catálogo.

Sin AWS: todo es puro y se prueba sin red.
"""

import re
from dataclasses import dataclass

from pos_dominio import ids
from pos_dominio.errores import Validacion

CATORCE_DIAS = 1_209_600


@dataclass(frozen=True)
class Canal:
    id: str
    tipo: str  # "flujo" | "cola" | "cola_fallidos" | "tema" | "programado"
    nombre_aws: str
    proposito: str
    productores: tuple[str, ...]
    consumidores: tuple[str, ...]
    variable: str | None = None  # variable de entorno con la URL o el ARN, en las funciones que lo usan
    fifo: bool = False
    visibilidad: int | None = None  # segundos
    max_recepciones: int | None = None  # antes de pasar a su cola de fallidos
    fallidos: str | None = None  # id del canal donde terminan los mensajes que no se pudieron procesar
    tratamiento: str = ""


CANALES: dict[str, Canal] = {c.id: c for c in (
    Canal("eventos", "flujo", "operacion (DynamoDB Streams)",
          "Cada cambio de negocio deja un evento en la misma transacción (outbox) y se procesa en segundo plano",
          ("salon", "pedidos", "caja", "administracion", "emision-dte", "drenador-contingencia", "mensajeria"),
          ("procesador-eventos",), fallidos="procesador-eventos-fallidos",
          tratamiento="Confirmación por registro; 10 reintentos dividiendo el lote; luego, destino ante fallo"),
    Canal("procesador-eventos-fallidos", "cola_fallidos", "procesador-eventos-fallidos",
          "Lotes del flujo de eventos que agotaron sus reintentos (para revisión)",
          ("destino ante fallo del flujo",), ("revisión técnica",), visibilidad=30),
    Canal("dte-emision", "cola", "dte-emision", "Emitir el documento tributario de cada venta",
          ("procesador-eventos", "tareas-programadas", "mensajeria (reproceso)"), ("emision-dte",),
          variable="COLA_DTE_URL", visibilidad=180, max_recepciones=5, fallidos="dte-emision-fallidos",
          tratamiento="Proveedor caído: reintento con espera creciente; rechazo de negocio: final, sin reintento"),
    Canal("dte-emision-fallidos", "cola_fallidos", "dte-emision-fallidos",
          "Documentos que agotaron sus 5 intentos (se reprocesan desde Administración → Mensajería)",
          ("dte-emision (redrive)",), ("revisión del dueño o admin",), visibilidad=30),
    Canal("contingencia-comandas", "cola", "contingencia-comandas.fifo",
          "Comandas aceptadas durante una falla; se reaplican en orden por mesa",
          ("pedidos", "contingencia", "mensajeria (reproceso)"), ("drenador-contingencia",),
          variable="COLA_CONTINGENCIA_URL", fifo=True, visibilidad=360, max_recepciones=15,
          fallidos="contingencia-comandas-fallidos",
          tratamiento="Falla de infraestructura: reintento (unos 90 min); rechazo de negocio: conflicto registrado"),
    Canal("contingencia-comandas-fallidos", "cola_fallidos", "contingencia-comandas-fallidos.fifo",
          "Comandas que no se pudieron reaplicar tras 15 intentos (se reprocesan desde Mensajería)",
          ("contingencia-comandas (redrive)",), ("revisión del dueño o admin",), fifo=True, visibilidad=30),
    Canal("avisos", "tema", "pos-avisos-dueno", "Avisos del negocio, distribuidos por reglas a cada destino",
          ("procesador-eventos", "tareas-programadas", "mensajeria (pruebas)"),
          ("destinos administrables (correo o cola)",), variable="TEMA_DUENO_ARN"),
    Canal("alertas", "tema", "pos-alertas-tecnicas", "Alertas técnicas para el equipo que opera la plataforma",
          ("procesador-eventos", "tareas-programadas", "alarmas de CloudWatch"), ("equipo técnico (correo)",),
          variable="TEMA_ALERTAS_ARN"),
    Canal("tareas", "programado", "pos-tareas-programadas",
          "Cada 5 minutos: reencola documentos atascados y vigila turnos e impresoras",
          ("EventBridge rate(5 minutes)",), ("tareas-programadas",)),
)}

COLAS_CON_REPROCESO = ("dte-emision", "contingencia-comandas")


@dataclass(frozen=True)
class Ruta:
    evento: str
    canal: str
    consumidor: str
    efecto: str
    condicion: str = ""


RUTAS: tuple[Ruta, ...] = (
    Ruta("todos los eventos", "eventos", "procesador-eventos", "Archivo histórico (consultable con Athena)"),
    Ruta("venta.cerrada", "eventos", "procesador-eventos", "Totales de reportes y comprobante interno"),
    Ruta("venta.cerrada", "dte-emision", "emision-dte", "Emisión del documento tributario"),
    Ruta("documento sin intentos por 15 minutos", "dte-emision", "emision-dte", "Reencolado por tareas-programadas"),
    Ruta("retiro.registrado", "eventos", "procesador-eventos", "Totales de reportes"),
    Ruta("comanda con la ruta normal caída", "contingencia-comandas", "drenador-contingencia",
         "Reaplicación en orden por mesa"),
    Ruta("turno.cerrado", "avisos", "destinos con la regla", "Aviso cierre_con_diferencia",
         "solo si hay diferencia de efectivo"),
    Ruta("dte.rechazado", "avisos", "destinos con la regla", "Aviso documento_rechazado"),
    Ruta("conflicto.registrado", "avisos", "destinos con la regla", "Aviso comanda_en_conflicto"),
    Ruta("autorizacion.rechazada", "avisos", "destinos con la regla", "Aviso autorizacion_bloqueada",
         "solo si el autorizador quedó bloqueado"),
    Ruta("turno abierto más de 18 horas", "avisos", "destinos con la regla", "Aviso turno_abierto_demasiado"),
    Ruta("dte.fallido", "alertas", "equipo técnico", "Alerta documento_fallido"),
    Ruta("impresora sin retirar trabajos por 10 minutos", "alertas", "equipo técnico", "Alerta impresora_sin_retirar"),
)


@dataclass(frozen=True)
class Aviso:
    id: str
    canal: str
    titulo: str
    descripcion: str

    @property
    def administrable(self) -> bool:
        """Solo los avisos del negocio se distribuyen a destinos administrables."""
        return self.canal == "avisos"


AVISOS: dict[str, Aviso] = {a.id: a for a in (
    Aviso("cierre_con_diferencia", "avisos", "Cierre de caja con diferencia",
          "Un turno cerró con diferencia entre el efectivo contado y el esperado"),
    Aviso("documento_rechazado", "avisos", "Documento tributario rechazado",
          "El proveedor rechazó la boleta o factura de una venta"),
    Aviso("comanda_en_conflicto", "avisos", "Comanda en conflicto",
          "Una comanda registrada durante una falla no se pudo aplicar"),
    Aviso("autorizacion_bloqueada", "avisos", "Código de autorización bloqueado",
          "Un código de dueño o admin se bloqueó tras 5 intentos fallidos"),
    Aviso("turno_abierto_demasiado", "avisos", "Turno abierto demasiado tiempo",
          "Un turno de caja lleva más de 18 horas abierto"),
    Aviso("documento_fallido", "alertas", "Documento tributario fallido",
          "Un documento agotó sus reintentos y quedó en la cola de fallidos"),
    Aviso("impresora_sin_retirar", "alertas", "Impresora sin retirar trabajos",
          "Una impresora no retira sus trabajos hace más de 10 minutos"),
)}

AVISOS_ADMINISTRABLES: tuple[str, ...] = tuple(a.id for a in AVISOS.values() if a.administrable)


def canal_de_aviso(aviso_id: str) -> Canal:
    return CANALES[AVISOS[aviso_id].canal]


def atributos_aviso(aviso_id: str, tenant_id: str, local_id: str, *, prueba: bool = False) -> dict[str, str]:
    """Atributos de cada mensaje publicado en un tema. Las reglas de los destinos filtran por ellos."""
    return {"aviso": aviso_id, "tenant_id": tenant_id, "local_id": local_id, "prueba": "si" if prueba else "no"}


def politica_de_filtro(tenant_id: str, local_id: str, avisos: list[str]) -> dict:
    """Regla de distribución de un destino: solo los avisos elegidos y solo de su local."""
    return {"aviso": sorted(avisos), "tenant_id": [tenant_id], "local_id": [local_id]}


def recibe(politica: dict, atributos: dict[str, str]) -> bool:
    """Misma semántica que el filtro de SNS que se configura: cada clave debe coincidir con un valor."""
    return all(atributos.get(clave) in valores for clave, valores in politica.items())


# --- validación de las solicitudes de administración ---------------------------------------------------

TIPOS_DESTINO = ("correo", "cola")
MAX_DESTINOS_POR_LOCAL = 10
_NOMBRE = re.compile(r"^[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ][0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ _\-]{0,59}$")
_CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$")
_CAMPOS_DESTINO = {"nombre", "tipo", "correo", "avisos"}


def _invalido(campo: str, mensaje: str, codigo: str = "CAMPO_INVALIDO") -> Validacion:
    return Validacion(mensaje, codigo=codigo, detalle={"campo": campo})


def normalizar_nombre(nombre: str) -> str:
    return " ".join(nombre.lower().split())


def validar_aviso(valor, campo: str = "aviso") -> str:
    if not isinstance(valor, str) or not valor:
        raise _invalido(campo, "Indica el aviso de la regla")
    if valor not in AVISOS:
        raise _invalido(campo, f"Aviso desconocido: {valor}. Opciones: {', '.join(AVISOS_ADMINISTRABLES)}",
                        "AVISO_DESCONOCIDO")
    if not AVISOS[valor].administrable:
        raise _invalido(campo, "Ese aviso es una alerta técnica del sistema y no se distribuye a destinos",
                        "AVISO_NO_ADMINISTRABLE")
    return valor


def validar_destino(cuerpo) -> dict:
    """Devuelve {nombre, tipo, correo?, avisos} normalizado o lanza Validacion con el campo culpable."""
    if not isinstance(cuerpo, dict):
        raise _invalido("cuerpo", "El cuerpo debe ser un objeto JSON")
    desconocidos = sorted(set(cuerpo) - _CAMPOS_DESTINO)
    if desconocidos:
        raise _invalido(desconocidos[0], f"Campo no permitido: {desconocidos[0]}", "CAMPO_DESCONOCIDO")

    nombre = cuerpo.get("nombre")
    if not isinstance(nombre, str) or not _NOMBRE.match(nombre.strip()):
        raise _invalido("nombre", "El nombre es obligatorio: de 1 a 60 letras, números, espacios, guiones o _",
                        "NOMBRE_INVALIDO")
    tipo = cuerpo.get("tipo")
    if tipo not in TIPOS_DESTINO:
        raise _invalido("tipo", "El tipo debe ser «correo» o «cola»", "TIPO_DESTINO_INVALIDO")

    datos = {"nombre": " ".join(nombre.split()), "tipo": tipo}
    correo = cuerpo.get("correo")
    if tipo == "correo":
        if not isinstance(correo, str) or len(correo) > 254 or not _CORREO.match(correo.strip()):
            raise _invalido("correo", "Indica un correo válido", "CORREO_INVALIDO")
        datos["correo"] = correo.strip().lower()
    elif correo is not None:
        raise _invalido("correo", "Un destino de tipo cola no lleva correo", "CAMPO_NO_CORRESPONDE")

    avisos = cuerpo.get("avisos")
    if not isinstance(avisos, list) or not avisos:
        raise _invalido("avisos", "Elige al menos un aviso (una regla de distribución)", "REGLAS_REQUERIDAS")
    vistos: list[str] = []
    for i, aviso in enumerate(avisos):
        aviso = validar_aviso(aviso, f"avisos[{i}]")
        if aviso in vistos:
            raise _invalido(f"avisos[{i}]", f"El aviso {aviso} está repetido", "REGLA_REPETIDA")
        vistos.append(aviso)
    datos["avisos"] = vistos
    return datos


def validar_destino_id(valor) -> str:
    if not isinstance(valor, str) or not ids.es_ulid(valor):
        raise _invalido("destino_id", "Destino inexistente", "DESTINO_ID_INVALIDO")
    return valor


def validar_canal_reproceso(valor) -> str:
    if valor not in COLAS_CON_REPROCESO:
        raise _invalido("canal", f"El canal debe ser uno de: {', '.join(COLAS_CON_REPROCESO)}", "CANAL_INVALIDO")
    return valor


def nombre_cola_destino(destino_id: str) -> str:
    """Nombre de la cola de un destino de tipo cola (SQS: hasta 80 caracteres, minúsculas permitidas)."""
    return f"pos-destino-{destino_id.lower()}"
