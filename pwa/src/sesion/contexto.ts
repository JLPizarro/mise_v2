import { createContext } from "react"
import type { LocalDeUsuario, Rol, Yo } from "@/api/tipos"
import type { EstadoSesion } from "@/sesion/google"

export interface ErrorAcceso { codigo: string; mensaje: string }

export interface ValorSesion {
  sesion: EstadoSesion
  /** Identidad y locales del usuario (de GET /yo, o de la sesión guardada en la estación sin conexión). */
  yo: Yo | null
  cargando: boolean
  errorAcceso: ErrorAcceso | null
  /** Falla de servicio al cargar /yo (no es falta de permiso): se puede reintentar. */
  errorCarga: string | null
  /** Local de la URL o, si no hay, el último elegido. */
  local: LocalDeUsuario | null
  rol: Rol | null
  /** Estación recargada sin internet: solo salón y comanda (P17). */
  sinConexionSoloLectura: boolean
  /** Hubo sesión pero el token venció: se muestra «Ingresar» sin perder lo que hay en pantalla. */
  vencida: boolean
  /** La persona salió a propósito: al volver a ingresar se parte del inicio, no de la última pantalla. */
  cerrada: boolean
  reintentar: () => void
  salir: () => void
}

export const SesionContexto = createContext<ValorSesion | null>(null)
