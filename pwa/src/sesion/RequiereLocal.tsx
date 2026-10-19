import { useEffect, type ReactNode } from "react"
import { Navigate, useParams } from "react-router-dom"
import { guardarLocal } from "@/sesion/localGuardado"
import { useSesion } from "@/sesion/useSesion"

/** El local de la URL debe ser uno de la persona; si no, vuelve al inicio. Lo recuerda como el último elegido. */
export function RequiereLocal({ children }: { children: ReactNode }) {
  const { yo } = useSesion()
  const { localId } = useParams()
  const valido = !!yo && !!localId && yo.locales.some((l) => l.local_id === localId)

  useEffect(() => {
    if (valido && localId) guardarLocal(localId)
  }, [valido, localId])

  if (!valido) return <Navigate to="/" replace />
  return <>{children}</>
}
