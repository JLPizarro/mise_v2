import { useSyncExternalStore } from "react"
import { estacionActiva, suscribirEstacion } from "@/offline/estacion"

/** El ID de la estación de caja que es este equipo en el local, o null si no es estación. */
export function useEstacion(localId: string | undefined): string | null {
  return useSyncExternalStore(suscribirEstacion, () => (localId ? estacionActiva(localId) : null))
}
