import type { Rol } from "@/api/tipos"

/** Qué roles ven cada pantalla (roles.py, sección 3.4 del plan). */
export const ROLES = {
  salon: ["dueno", "admin", "cajero", "garzon"],
  bloquear: ["dueno", "admin", "cajero"],
  asignarGarzon: ["dueno", "admin"],
  caja: ["dueno", "admin", "cajero"],
  admin: ["dueno", "admin"],
} as const satisfies Record<string, readonly Rol[]>

export const NOMBRE_ROL: Record<Rol, string> = {
  dueno: "Dueño", admin: "Administrador", cajero: "Cajero", garzon: "Garzón", cocina: "Cocina",
}

/** Inicio por defecto del rol dentro de un local, o null si el rol no tiene pantalla en la PWA. */
export function inicioDelRol(rol: Rol, localId: string): string | null {
  const base = `/l/${localId}`
  if (rol === "dueno" || rol === "admin") return `${base}/admin`
  if (rol === "cajero") return `${base}/caja`
  if (rol === "garzon") return `${base}/salon`
  return null
}

export const puede = (rol: Rol | null, permitidos: readonly Rol[]): boolean => rol !== null && permitidos.includes(rol)
