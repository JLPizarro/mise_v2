"""Reglas puras de montos. Todo en pesos enteros; nunca float.

Origen de cada regla (caracterizada en tests/caracterizacion):
- partes iguales, por ítems, monto libre, propina sugerida y pago mixto venían del frontend
  (PendientesCaja.tsx, FormularioPago.tsx). Se mueven aquí para que el servidor las valide.
- el umbral del arqueo venía de caja_use_cases.calcular_umbral_diferencia.
"""

from fractions import Fraction

from pos_dominio.errores import Validacion

MIN_PERSONAS = 2   # DivisionPartesIguales.tsx: Math.max(2, ...)
MAX_PERSONAS = 20  # DivisionPartesIguales.tsx: Math.min(20, ...)


def propina_sugerida(monto: int, porcentaje: int) -> int:
    """round_half_up(monto * pct / 100), igual que Math.round de JavaScript para montos >= 0.

    No se usa round() de Python: redondea al par (100,5 -> 100), y el POS local mostraba 101."""
    if monto < 0 or porcentaje < 0:
        raise Validacion("monto y porcentaje no pueden ser negativos")
    return (monto * porcentaje + 50) // 100


def dividir_partes_iguales(total: int, personas: int) -> list[int]:
    """Base = total // n; el resto se reparte de a $1 en las primeras partes.

    Cambio respecto del local (D22): si hay más personas que pesos, el local creaba partes de $0
    que después no se podían cobrar. Aquí se rechaza."""
    if not MIN_PERSONAS <= personas <= MAX_PERSONAS:
        raise Validacion(f"La cuenta se divide entre {MIN_PERSONAS} y {MAX_PERSONAS} personas",
                         codigo="PERSONAS_FUERA_DE_RANGO")
    if total < personas:
        raise Validacion("El saldo es menor que la cantidad de personas: alguna parte quedaría en $0",
                         codigo="PARTE_EN_CERO")
    base, resto = divmod(total, personas)
    return [base + (1 if i < resto else 0) for i in range(personas)]


def agrupar_seleccion(seleccion: list[tuple[str, int]]) -> dict[str, int]:
    """Suma las cantidades de un mismo ítem repetido en la selección.

    Cambio (D23): el local validaba cada línea por separado y permitía cobrar 4 unidades de un
    ítem de 3 si venía repetido."""
    agrupado: dict[str, int] = {}
    for item_id, cantidad in seleccion:
        agrupado[item_id] = agrupado.get(item_id, 0) + cantidad
    return agrupado


def monto_por_items(disponibles: dict[str, tuple[int, int]], seleccion: dict[str, int], saldo: int) -> int:
    """Monto a cobrar por una selección de ítems: mín(Σ precio_congelado × cantidad, saldo).

    `disponibles` mapea item_id -> (unidades sin cobrar, precio_unitario congelado). Se usa siempre
    el precio congelado (D24: la vista previa del local usaba el precio actual del catálogo)."""
    total = 0
    for item_id, cantidad in seleccion.items():
        unidades, precio = disponibles[item_id]
        if cantidad > unidades:
            raise Validacion("La cantidad cobrada excede lo disponible para ese ítem",
                             codigo="ITEM_SIN_UNIDADES", detalle={"item_id": item_id, "disponibles": unidades})
        total += precio * cantidad
    return min(total, saldo)


def completar_ultimo_medio(total: int, montos_previos: list[int]) -> int:
    """En pago mixto, el último medio cubre lo que falta (FormularioPago.obtenerMontoConsumo)."""
    return max(total - sum(montos_previos), 0)


def umbral_diferencia(esperado: int, umbral_pb: int, minimo: int) -> int:
    """Diferencia tolerada en el arqueo antes de exigir un segundo conteo ciego.

    máx(round(esperado × pct / 100), mínimo), con el porcentaje en puntos base (2 % = 200).
    Conserva el redondeo al par del round() de Python que usa el local (ver D11), pero con
    aritmética exacta en vez de float."""
    return max(round(Fraction(esperado * umbral_pb, 10_000)), minimo)
