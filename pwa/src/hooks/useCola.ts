import { useEffect, useState, useSyncExternalStore } from "react"
import { cola } from "@/offline/cola"
import { estacionActiva } from "@/offline/estacion"
import { sincronizacion } from "@/offline/sincronizar"

/** Cantidad de comandas guardadas en este equipo para un local. */
export function useComandasGuardadas(localId: string | undefined): number {
  const [cantidad, setCantidad] = useState(0)
  useEffect(() => {
    if (!localId || estacionActiva(localId) === null) return
    let vigente = true
    const leer = () => void cola.contar(localId).then((n) => vigente && setCantidad(n))
    leer()
    const baja = cola.suscribir(leer)
    return () => {
      vigente = false
      baja()
    }
  }, [localId])
  return localId ? cantidad : 0
}

/** Cantidad de mesas con comandas aceptadas en contingencia que el servidor aún no refleja. */
export function useMesasSincronizando(): number {
  return useSyncExternalStore(sincronizacion.suscribir, sincronizacion.total)
}
