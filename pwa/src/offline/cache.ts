import { db } from "@/offline/db"
import { estacionActiva } from "@/offline/estacion"

/** Claves: plano:<local>, carta:<local>, pedido:<local>:<pedido_id>, sesion_estacion:<local>. */
const localDe = (clave: string): string => clave.split(":")[1] ?? ""

/** Solo se escribe en una estación de caja: los celulares no guardan nada (P16). */
export async function guardarCache(clave: string, valor: unknown): Promise<void> {
  if (estacionActiva(localDe(clave)) === null) return
  await (await db()).put("cache", { clave, valor, guardadoEn: Date.now() })
}

export async function leerCache<T>(clave: string, maxEdadMs?: number): Promise<T | null> {
  if (estacionActiva(localDe(clave)) === null) return null // ni siquiera se abre IndexedDB fuera de la estación
  const entrada = await (await db()).get("cache", clave)
  if (!entrada) return null
  if (maxEdadMs !== undefined && Date.now() - entrada.guardadoEn > maxEdadMs) return null
  return entrada.valor as T
}
