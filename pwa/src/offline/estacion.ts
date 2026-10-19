import type { LocalDeUsuario } from "@/api/tipos"
import { guardarCache, leerCache } from "@/offline/cache"
import { cola } from "@/offline/cola"

const DOCE_HORAS_MS = 12 * 3600_000
const clave = (localId: string) => `pos.estacion.${localId}`

const oyentes = new Set<() => void>()
const avisar = () => oyentes.forEach((o) => o())
/** Para useEstacion: avisa cuando este equipo se registra o deja de ser estación. */
export function suscribirEstacion(oyente: () => void): () => void {
  oyentes.add(oyente)
  return () => { oyentes.delete(oyente) }
}

export interface SesionDeEstacion { local: LocalDeUsuario; sub: string; nombre: string }

export function estacionActiva(localId: string): string | null {
  try {
    return localStorage.getItem(clave(localId))
  } catch {
    return null
  }
}

/** `sesion` es opcional: si falta, se guarda en el siguiente GET /yo. */
export async function activarEstacion(localId: string, estacionId: string, sesion?: SesionDeEstacion): Promise<void> {
  localStorage.setItem(clave(localId), estacionId)
  if (sesion) await guardarSesionDeEstacion(localId, sesion.local, sesion.sub, sesion.nombre)
  avisar()
}

export async function desactivarEstacion(localId: string): Promise<void> {
  if ((await cola.contar(localId)) > 0) {
    throw new Error("Envía o descarta las comandas guardadas antes de desactivar la estación")
  }
  localStorage.removeItem(clave(localId))
  avisar()
}

/** Se llama después de cada GET /yo exitoso en la estación. Nunca guarda el token. */
export async function guardarSesionDeEstacion(localId: string, local: LocalDeUsuario, sub: string, nombre: string): Promise<void> {
  await guardarCache(`sesion_estacion:${localId}`, { local, sub, nombre } satisfies SesionDeEstacion)
}

export async function sesionDeEstacion(localId: string): Promise<SesionDeEstacion | null> {
  return leerCache<SesionDeEstacion>(`sesion_estacion:${localId}`, DOCE_HORAS_MS)
}
