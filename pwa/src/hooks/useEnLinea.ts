import { useSyncExternalStore } from "react"
import { red } from "@/offline/red"

/** true cuando la API responde; false cuando se perdió la conexión. */
export function useEnLinea(): boolean {
  return useSyncExternalStore(red.suscribir, () => red.estado() === "en_linea")
}
