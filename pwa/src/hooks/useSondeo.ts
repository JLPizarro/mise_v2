import { useEffect, useRef } from "react"
import { red } from "@/offline/red"

/**
 * Ejecuta `tarea` cada `cadaMs` solo con la pestaña visible y en línea (P18). Al volver a ser visible
 * corre una vez de inmediato. `activo = false` lo detiene.
 */
export function useSondeo(tarea: () => void | Promise<void>, cadaMs: number, activo = true): void {
  const ultima = useRef(tarea)
  useEffect(() => {
    ultima.current = tarea
  })
  useEffect(() => {
    if (!activo) return
    const correr = () => {
      if (document.visibilityState === "visible" && !red.sinConexion()) void ultima.current()
    }
    const id = window.setInterval(correr, cadaMs)
    document.addEventListener("visibilitychange", correr)
    return () => {
      window.clearInterval(id)
      document.removeEventListener("visibilitychange", correr)
    }
  }, [cadaMs, activo])
}
