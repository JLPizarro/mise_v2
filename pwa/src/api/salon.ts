import { leer, pedir } from "@/api/cliente"
import { crearComando, type Comando } from "@/api/comandos"
import { L } from "@/api/rutas"
import type { Carta, EstadoMesaSolo, Plano, Yo } from "@/api/tipos"

export const salud = (): Promise<unknown> => pedir("GET", "/salud", { publica: true }).then((r) => r.datos)

export const yo = (): Promise<Yo> => leer<Yo>("/yo")

export const plano = (localId: string): Promise<Plano> => leer<Plano>(`${L(localId)}/salon`)

export const estadoDelPlano = (localId: string): Promise<{ mesas: EstadoMesaSolo[] }> =>
  leer(`${L(localId)}/salon`, { solo_estado: "1" })

/** Con `version` guardada responde `{version, sin_cambios: true}` si la carta no cambió. */
export const carta = (localId: string, version?: number): Promise<Carta | { version: number; sin_cambios: true }> =>
  leer(`${L(localId)}/catalogo`, { version: version === undefined ? undefined : String(version) })

export const bloquearMesa = (localId: string, mesaId: string, bloqueada: boolean): Comando =>
  crearComando(localId, "POST", `${L(localId)}/mesas/${mesaId}/bloqueo`, { mesa_id: mesaId, bloqueada })

export const asignarGarzon = (localId: string, mesaId: string, garzonId: string | null): Comando =>
  crearComando(localId, "POST", `${L(localId)}/mesas/${mesaId}/garzon`, { mesa_id: mesaId, garzon_id: garzonId })
