import { useMemo, useState } from "react"
import type { Pedido, TipoDivision } from "@/api/tipos"
import { aEntero, dividirPartesIguales, montoPorItems } from "@/lib/dinero"

/**
 * Estado de la división de la cuenta para un cobro. Qué parte ya se pagó (partes iguales) vive
 * solo en memoria, como en el POS anterior.
 */
export function useDivision(pedido: Pedido) {
  const [tipo, setTipo] = useState<TipoDivision>("completa")
  const [seleccion, setSeleccion] = useState<Record<string, number>>({})
  const [personas, setPersonas] = useState(2)
  const [partes, setPartes] = useState<number[] | null>(null)
  const [pagadas, setPagadas] = useState(0)
  const [libre, setLibre] = useState("")
  const saldo = pedido.saldo

  const itemsCobrados = useMemo(
    () => Object.entries(seleccion).filter(([, c]) => c > 0).map(([item_id, cantidad]) => ({ item_id, cantidad })),
    [seleccion],
  )

  let monto = 0
  let error: string | null = null
  if (tipo === "completa") {
    monto = saldo
  } else if (tipo === "items") {
    try {
      monto = itemsCobrados.length > 0 ? montoPorItems(pedido.items, itemsCobrados, saldo) : 0
    } catch (e) {
      error = e instanceof Error ? e.message : "Selección inválida"
    }
  } else if (tipo === "partes_iguales") {
    if (partes && pagadas < partes.length) monto = Math.min(partes[pagadas], saldo)
  } else {
    const n = aEntero(libre)
    if (libre !== "" && (n === null || n < 1 || n > saldo)) error = `El monto debe estar entre $1 y el saldo`
    else monto = n ?? 0
  }

  function dividir(): void {
    try {
      setPartes(dividirPartesIguales(saldo, personas))
      setPagadas(0)
    } catch (e) {
      setPartes(null)
      throw e
    }
  }

  /** Después de un pago registrado: limpia lo que ya se cobró. */
  function alPagar(): void {
    setSeleccion({})
    setLibre("")
    if (tipo === "partes_iguales") setPagadas((p) => p + 1)
  }

  return {
    tipo, setTipo, seleccion, setSeleccion, personas, setPersonas, partes, pagadas, libre, setLibre,
    monto, error, itemsCobrados, dividir, alPagar,
  }
}

export type Division = ReturnType<typeof useDivision>
