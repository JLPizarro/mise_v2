import { createContext, useContext } from "react"

export type TipoAviso = "ok" | "info" | "error"
export interface Notificar { (texto: string, tipo?: TipoAviso): void }

export const NotificacionesContexto = createContext<Notificar | null>(null)

/** `notificar("texto")` muestra un aviso breve (toast). */
export function useNotificar(): Notificar {
  const valor = useContext(NotificacionesContexto)
  if (!valor) throw new Error("useNotificar se usa dentro de Notificaciones")
  return valor
}
