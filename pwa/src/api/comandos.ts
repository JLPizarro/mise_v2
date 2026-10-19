import { ErrorApi, pedir, SinConexion, type Respuesta } from "@/api/cliente"
import type { Item } from "@/api/tipos"
import { ulid } from "@/lib/ulid"
import { cola } from "@/offline/cola"
import { estacionActiva } from "@/offline/estacion"
import { red } from "@/offline/red"
import { sincronizacion } from "@/offline/sincronizar"

export const OPERACIONES_COMANDA = [
  "pedido.abrir", "pedido.agregar_item", "pedido.modificar_item", "pedido.quitar_item",
  "pedido.enviar_tanda", "pedido.precuenta", "pedido.reabrir",
] as const
export type OperacionComanda = (typeof OPERACIONES_COMANDA)[number]

/** Datos para mostrar un ítem agregado antes de que el servidor responda. No se envían. */
export type VistaItem = Pick<Item, "nombre" | "categoria" | "cuarto_id" | "precio_unitario" | "modificador_nombre">

export interface Comando {
  readonly id: string
  readonly localId: string
  readonly metodo: "POST" | "PATCH" | "DELETE"
  readonly ruta: string
  readonly cuerpo: Readonly<Record<string, unknown>>
  readonly operacion: OperacionComanda | null
  readonly mesaId: string | null
  readonly creadoEn: string
  readonly vistaItem?: VistaItem
}

export function crearComando(
  localId: string, metodo: Comando["metodo"], ruta: string, cuerpo: Record<string, unknown>,
  operacion: OperacionComanda | null = null, vistaItem?: VistaItem,
): Comando {
  const limpio = Object.fromEntries(Object.entries(cuerpo).filter(([, v]) => v !== undefined))
  return Object.freeze({
    id: ulid(), localId, metodo, ruta, cuerpo: Object.freeze(limpio), operacion,
    mesaId: typeof limpio.mesa_id === "string" ? limpio.mesa_id : null,
    creadoEn: new Date().toISOString(), vistaItem,
  })
}

export type Resultado<T> =
  | { via: "normal"; respuesta: Respuesta<T> }
  | { via: "contingencia" }
  | { via: "cola_local" }

const esperar = (ms: number) => new Promise((r) => window.setTimeout(r, ms))
const esFalla = (e: unknown): boolean => e instanceof SinConexion || (e instanceof ErrorApi && e.esFallaDeServicio)

export async function ejecutar<T>(c: Comando): Promise<Resultado<T>> {
  const comanda = c.operacion !== null
  const estacion = comanda && estacionActiva(c.localId) !== null
  // Sin conexión, o con comandas ya guardadas, la estación sigue guardando en orden.
  if (estacion && (red.sinConexion() || (await cola.contar(c.localId)) > 0)) {
    await cola.agregar(c)
    return { via: "cola_local" }
  }
  if (comanda && c.mesaId && sincronizacion.activa(c.localId, c.mesaId)) return porContingencia<T>(c)

  let ultimo: unknown = null
  for (let intento = 0; intento < 2; intento++) {
    try {
      const respuesta = await pedir<T>(c.metodo, c.ruta, { cuerpo: c.cuerpo, commandId: c.id })
      if (respuesta.http === 202) {
        sincronizacion.registrar(c)
        return { via: "contingencia" }
      }
      return { via: "normal", respuesta }
    } catch (e) {
      if (e instanceof ErrorApi && e.codigo === "CONFLICTO_CONCURRENCIA" && intento === 0) {
        await esperar(300)
        continue
      }
      if (!esFalla(e)) throw e
      ultimo = e
      if (e instanceof SinConexion && !navigator.onLine) break
      if (intento === 0) await esperar(1000)
    }
  }
  if (!comanda) throw ultimo instanceof SinConexion ? new SinConexion("Sin conexión: esta acción necesita internet") : ultimo
  return porContingencia<T>(c)
}

async function porContingencia<T>(c: Comando): Promise<Resultado<T>> {
  try {
    await pedir("POST", "/contingencia/comandas", {
      cuerpo: { operacion: c.operacion, local_id: c.localId, cuerpo: c.cuerpo, ocurrido_en: c.creadoEn },
      commandId: c.id,
    })
    sincronizacion.registrar(c)
    return { via: "contingencia" }
  } catch (e) {
    if (!esFalla(e)) throw e
    if (estacionActiva(c.localId) !== null) {
      await cola.agregar(c)
      return { via: "cola_local" }
    }
    throw new SinConexion("Sin conexión: usa la caja")
  }
}
