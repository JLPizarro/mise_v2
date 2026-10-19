import { leer } from "@/api/cliente"
import { crearComando, type Comando } from "@/api/comandos"
import { L } from "@/api/rutas"

export type Recurso =
  | "sectores" | "mesas" | "productos" | "cuartos" | "impresoras" | "materias-primas" | "recetas"
  | "configuracion" | "personal" | "invitaciones" | "mi-codigo" | "estaciones"

/** El email de una invitación va en la ruta: se codifica pero se deja la @. */
export const idDeEmail = (email: string): string => encodeURIComponent(email).replace(/%40/g, "@")

const base = (localId: string, recurso: Recurso) => `${L(localId)}/admin/${recurso}`

export const listar = <T = Record<string, unknown>>(localId: string, recurso: Recurso): Promise<T> =>
  leer<T>(base(localId, recurso))

/** Los cuerpos llevan solo los campos: el servidor pone el ID de la ruta. */
export const crear = (localId: string, recurso: Recurso, cuerpo: Record<string, unknown>): Comando =>
  crearComando(localId, "POST", base(localId, recurso), cuerpo)

export const editar = (localId: string, recurso: Recurso, id: string, cuerpo: Record<string, unknown>): Comando =>
  crearComando(localId, "PATCH", `${base(localId, recurso)}/${id}`, cuerpo)

export const eliminar = (localId: string, recurso: Recurso, id: string): Comando =>
  crearComando(localId, "DELETE", `${base(localId, recurso)}/${id}`, {})

/** Por ejemplo, `accion(local, "impresoras", id, "rotar-clave")`. */
export const accion = (localId: string, recurso: Recurso, id: string, nombre: string): Comando =>
  crearComando(localId, "POST", `${base(localId, recurso)}/${id}/${nombre}`, {})
