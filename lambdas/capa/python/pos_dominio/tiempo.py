"""Hora y fecha operativa.

Todas las horas se guardan en UTC con milisegundos. La fecha operativa es la fecha en Chile, que
decide la partición del archivo histórico y el agregado diario.

Riesgo R3: el runtime de Lambda puede no traer la base de zonas horarias. Por eso la capa incluye
el archivo de America/Santiago (datos/America_Santiago, tomado del paquete tzdata, dominio público)
y se usa si la zona del sistema no está. /salud informa cuál se usó.
"""

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ZONA = "America/Santiago"
_ARCHIVO_ZONA = Path(__file__).parent / "datos" / "America_Santiago"


@lru_cache(maxsize=1)
def _zona() -> tuple[ZoneInfo, str]:
    try:
        return ZoneInfo(ZONA), "sistema"
    except ZoneInfoNotFoundError:
        with open(_ARCHIVO_ZONA, "rb") as archivo:
            return ZoneInfo.from_file(archivo, key=ZONA), "capa"


def zona_chile() -> ZoneInfo:
    return _zona()[0]


def fuente_zona() -> str:
    return _zona()[1]


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(momento: datetime) -> str:
    momento = momento.astimezone(timezone.utc)
    return momento.strftime("%Y-%m-%dT%H:%M:%S.") + f"{momento.microsecond // 1000:03d}Z"


def desde_iso(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def fecha_operativa(momento: datetime) -> str:
    return momento.astimezone(zona_chile()).strftime("%Y-%m-%d")


def epoch(momento: datetime) -> int:
    return int(momento.timestamp())
