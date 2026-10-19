import { useCallback, useEffect, useState } from "react"
import { estadoDelPlano, plano as pedirPlano } from "@/api/salon"
import type { EstadoMesaSolo, Plano } from "@/api/tipos"
import { useSondeo } from "@/hooks/useSondeo"
import { guardarCache, leerCache } from "@/offline/cache"
import { estacionActiva } from "@/offline/estacion"
import { useSesion } from "@/sesion/useSesion"
import { mensajeDeError } from "@/hooks/useComando"

/**
 * El plano de un local: se carga completo al entrar y luego solo el estado de las mesas cada 10 s (P18).
 * En la estación se guarda en caché y, sin conexión, se usa lo último guardado.
 */
export function usePlano(localId: string) {
  const { sesion } = useSesion()
  const hayToken = sesion.token !== null
  const [plano, setPlano] = useState<Plano | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [desdeCache, setDesdeCache] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await pedirPlano(localId)
      setPlano(datos)
      setDesdeCache(false)
      setError(null)
      await guardarCache(`plano:${localId}`, datos)
    } catch (e) {
      if (estacionActiva(localId) !== null) {
        const guardado = await leerCache<Plano>(`plano:${localId}`)
        if (guardado) {
          setPlano(guardado)
          setDesdeCache(true)
          setError(null)
          return
        }
      }
      setError(mensajeDeError(e))
    }
  }, [localId])

  useEffect(() => {
    // Sin token (estación sin conexión) igual se intenta: cae a la caché.
    if (hayToken || estacionActiva(localId) !== null) void cargar()
  }, [cargar, hayToken, localId])

  const mezclar = useCallback((estados: EstadoMesaSolo[]) => {
    setPlano((actual) =>
      actual && {
        ...actual,
        mesas: actual.mesas.map((m) => {
          const nuevo = estados.find((x) => x.mesa_id === m.mesa_id)
          return nuevo ? { ...m, ...nuevo } : m
        }),
      },
    )
  }, [])

  useSondeo(async () => {
    try {
      mezclar((await estadoDelPlano(localId)).mesas)
      setDesdeCache(false)
    } catch {
      /* se reintenta en el próximo ciclo */
    }
  }, 10_000, plano !== null && hayToken)

  return { plano, error, desdeCache, recargar: cargar, mezclar }
}
