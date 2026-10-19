import { ejecutar, type Comando } from "@/api/comandos"

/**
 * Ejecuta una escritura que no es de comanda (caja, salón, administración). Solo hay vía normal:
 * si falla el servicio, `ejecutar` lanza (no hay contingencia ni cola para estas operaciones).
 * La pantalla conserva el mismo `Comando` para reintentar con el mismo X-Command-Id.
 */
export async function escribir<T>(c: Comando): Promise<T> {
  const r = await ejecutar<T>(c)
  if (r.via !== "normal") throw new Error("Respuesta inesperada del servicio")
  return r.respuesta.datos
}
