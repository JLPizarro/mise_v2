import { useCallback, useEffect, useState } from "react"
import { carta as pedirCarta } from "@/api/salon"
import type { Carta } from "@/api/tipos"
import { useSondeo } from "@/hooks/useSondeo"
import { guardarCache, leerCache } from "@/offline/cache"
import { estacionActiva } from "@/offline/estacion"
import { useSesion } from "@/sesion/useSesion"

/** Última carta vista por local, solo en memoria (los celulares no guardan nada). */
const enMemoria = new Map<string, Carta>()

/** La carta con `?version=`: al entrar y cada 5 minutos (P18). Solo productos activos. */
export function useCarta(localId: string) {
  const { sesion } = useSesion()
  const hayToken = sesion.token !== null
  const [carta, setCarta] = useState<Carta | null>(enMemoria.get(localId) ?? null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    const guardada = enMemoria.get(localId) ?? (await leerCache<Carta>(`carta:${localId}`)) ?? undefined
    try {
      const respuesta = await pedirCarta(localId, guardada?.version)
      if ("sin_cambios" in respuesta && guardada) {
        enMemoria.set(localId, guardada)
        setCarta(guardada)
      } else if (!("sin_cambios" in respuesta)) {
        enMemoria.set(localId, respuesta)
        setCarta(respuesta)
        await guardarCache(`carta:${localId}`, respuesta)
      }
      setError(null)
    } catch (e) {
      if (guardada && estacionActiva(localId) !== null) {
        setCarta(guardada)
        return
      }
      if (!enMemoria.has(localId)) setError(e instanceof Error ? e.message : "No se pudo cargar la carta")
    }
  }, [localId])

  useEffect(() => {
    if (hayToken || estacionActiva(localId) !== null) void cargar()
  }, [cargar, hayToken, localId])

  useSondeo(cargar, 5 * 60_000, hayToken)

  return { productos: carta?.productos.filter((p) => p.activo) ?? [], cargada: carta !== null, error }
}
