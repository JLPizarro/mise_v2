"""Documento tributario electrónico (simulado) detrás del puerto EmisorDTE.

Máquina de estados en DTE#venta_id:  pendiente → enviando → emitido | rechazado | fallido

- El cobro nunca espera al documento: finalizar crea el DTE en `pendiente` y el flujo de eventos lo
  manda a la cola dte-emision.
- Un rechazo de negocio del proveedor (por ejemplo, datos del receptor inválidos) marca `rechazado`,
  no se reintenta y avisa al dueño.
- 429, 5xx y tiempo agotado se reintentan con espera creciente (se ajusta la visibilidad del
  mensaje). En la última recepción permitida se marca `fallido` y SQS lo mueve a la cola de fallidos.

Para cambiar al proveedor real basta otra clase con el método `emitir`; el dominio no cambia.
"""

import hashlib
import random
import time
from dataclasses import dataclass

MODOS = ("ok", "lento", "timeout", "error5xx", "limite429", "rechazo")
ESPERA_BASE_S = 30
ESPERA_MAXIMA_S = 900


class ErrorProveedor(Exception):
    """Falla transitoria del proveedor: se reintenta."""

    def __init__(self, tipo: str):
        super().__init__(f"proveedor DTE: {tipo}")
        self.tipo = tipo


@dataclass
class ResultadoEmision:
    aceptado: bool
    timbre: str | None = None
    motivo: str | None = None


class EmisorSimulado:
    """Proveedor simulado configurable por variables de entorno.

    DTE_MODO: ok | lento | timeout | error5xx | limite429 | rechazo
    DTE_TASA_FALLA: probabilidad (0 a 1) de que ocurra la falla del modo en cada intento. Por defecto 1.
    DTE_LATENCIA_MS: espera antes de responder. En `lento`, por defecto 3000.
    """

    def __init__(self, modo: str = "ok", tasa_falla: float = 1.0, latencia_ms: int = 0, *,
                 aleatorio=random.random, dormir=time.sleep):
        if modo not in MODOS:
            raise ValueError(f"DTE_MODO inválido: {modo}")
        self.modo = modo
        self.tasa_falla = min(max(tasa_falla, 0.0), 1.0)
        self.latencia_ms = latencia_ms or (3000 if modo == "lento" else 0)
        self._aleatorio = aleatorio
        self._dormir = dormir

    @classmethod
    def desde_entorno(cls, entorno: dict) -> "EmisorSimulado":
        return cls(entorno.get("DTE_MODO", "ok"), float(entorno.get("DTE_TASA_FALLA", "1") or 1),
                   int(entorno.get("DTE_LATENCIA_MS", "0") or 0))

    def emitir(self, documento: dict, folio: int) -> ResultadoEmision:
        if self.latencia_ms:
            self._dormir(self.latencia_ms / 1000)
        falla = self.modo not in ("ok", "lento") and self._aleatorio() < self.tasa_falla
        if falla and self.modo == "rechazo":
            return ResultadoEmision(False, motivo="Rechazo simulado: el receptor no está habilitado para recibir el documento")
        if falla:
            raise ErrorProveedor(self.modo)
        semilla = f"{documento['venta_id']}|{documento['tipo']}|{folio}|{documento['total']}"
        return ResultadoEmision(True, timbre=hashlib.sha256(semilla.encode()).hexdigest()[:40])


def espera_reintento(recepcion: int, aleatorio=random.random) -> int:
    """Segundos de espera antes del siguiente intento: 30, 60, 120... con tope y algo de azar."""
    base = min(ESPERA_BASE_S * 2 ** max(recepcion - 1, 0), ESPERA_MAXIMA_S)
    return int(base * (0.8 + 0.4 * aleatorio()))
