import { cola } from "@/offline/cola"
import { estacionActiva } from "@/offline/estacion"
import { red } from "@/offline/red"

/** true si una comanda de este local se guardaría en la cola local (estación sin conexión o con comandas ya guardadas). */
export async function iraALaCola(localId: string): Promise<boolean> {
  return estacionActiva(localId) !== null && (red.sinConexion() || (await cola.contar(localId)) > 0)
}
