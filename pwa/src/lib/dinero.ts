import type { Item } from "@/api/tipos"

const CLP = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 })
export const pesos = (monto: number): string => CLP.format(monto)

/** round_half_up(monto * pct / 100), igual que el servidor. */
export const propinaSugerida = (monto: number, pct: number): number => Math.floor((monto * pct + 50) / 100)

export function dividirPartesIguales(total: number, personas: number): number[] {
  if (personas < 2 || personas > 20) throw new Error("La cuenta se divide entre 2 y 20 personas")
  if (total < personas) throw new Error("El saldo es menor que la cantidad de personas: alguna parte quedaría en $0")
  const base = Math.floor(total / personas)
  const resto = total % personas
  return Array.from({ length: personas }, (_, i) => base + (i < resto ? 1 : 0))
}

/** mín(Σ precio congelado × cantidad, saldo); suma antes las líneas repetidas del mismo ítem. */
export function montoPorItems(items: Item[], seleccion: { item_id: string; cantidad: number }[], saldo: number): number {
  const agrupado = new Map<string, number>()
  for (const s of seleccion) agrupado.set(s.item_id, (agrupado.get(s.item_id) ?? 0) + s.cantidad)
  let total = 0
  for (const [itemId, cantidad] of agrupado) {
    const item = items.find((i) => i.item_id === itemId)
    if (!item) throw new Error("Uno de los ítems no pertenece a este pedido")
    if (cantidad > item.cantidad - item.cobrado) throw new Error("La cantidad cobrada excede lo disponible para ese ítem")
    total += item.precio_unitario * cantidad
  }
  return Math.min(total, saldo)
}

export const milesimas = (valor: number): string =>
  (valor / 1000).toLocaleString("es-CL", { maximumFractionDigits: 3 })

/** Texto de un campo de pesos → entero. Nunca parseFloat para dinero; vacío → null. */
export function aEntero(texto: string): number | null {
  const digitos = texto.replace(/\D/g, "")
  return digitos === "" ? null : Number.parseInt(digitos, 10)
}

/** Cantidad con hasta 3 decimales (la API recibe decimales y devuelve milésimas). Vacío o inválido → null. */
export function aDecimal(texto: string): number | null {
  const limpio = texto.trim().replace(",", ".")
  return /^\d+(\.\d{1,3})?$/.test(limpio) ? Number(limpio) : null
}
