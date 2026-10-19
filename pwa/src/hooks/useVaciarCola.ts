import { useCallback, useEffect } from "react"
import { useNotificar } from "@/components/comun/avisos"
import { useComandasGuardadas } from "@/hooks/useCola"
import { useEnLinea } from "@/hooks/useEnLinea"
import { useSondeo } from "@/hooks/useSondeo"
import { vaciarCola } from "@/offline/sincronizar"
import { useSesion } from "@/sesion/useSesion"

/**
 * Disparadores de `vaciarCola` (solo en la estación): al volver internet, al recuperar la sesión,
 * cada 30 s si hay comandas guardadas, y con «Enviar ahora».
 */
export function useVaciarCola(localId: string | undefined, esEstacion: boolean) {
  const notificar = useNotificar()
  const enLinea = useEnLinea()
  const { sesion } = useSesion()
  const hayToken = sesion.token !== null
  const pendientes = useComandasGuardadas(esEstacion ? localId : undefined)

  const enviarAhora = useCallback(async () => {
    if (!localId || !esEstacion) return
    const enviados = await vaciarCola(localId)
    if (enviados > 0) {
      notificar(enviados === 1 ? "1 comanda enviada a la nube" : `${enviados} comandas enviadas a la nube`, "ok")
    }
  }, [localId, esEstacion, notificar])

  useEffect(() => {
    if (esEstacion && enLinea && hayToken) void enviarAhora()
  }, [esEstacion, enLinea, hayToken, enviarAhora])

  useSondeo(enviarAhora, 30_000, esEstacion && pendientes > 0)

  return { enviarAhora, pendientes }
}
