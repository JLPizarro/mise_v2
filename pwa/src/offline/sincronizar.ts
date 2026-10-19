import { ErrorApi, leer, pedir, SesionRequerida, SinConexion } from "@/api/cliente"
import type { Comando } from "@/api/comandos"
import type { Conflicto, Pedido } from "@/api/tipos"
import { cola } from "@/offline/cola"
import { aplicar, huella } from "@/offline/pedidoLocal"
import { tokenVigente } from "@/sesion/google"

interface Registro { localId: string; mesaId: string; pedidoId: string | null; comandos: Comando[]; desde: number }
const registros = new Map<string, Registro>()
const oyentes = new Set<() => void>()
let version = 0
const avisar = () => {
  version++
  oyentes.forEach((o) => o())
}
const clave = (localId: string, mesaId: string) => `${localId}#${mesaId}`
export const ESPERA_MAXIMA_MS = 120_000

export const sincronizacion = {
  suscribir(oyente: () => void): () => void {
    oyentes.add(oyente)
    return () => { oyentes.delete(oyente) }
  },
  activa: (localId: string, mesaId: string): boolean => registros.has(clave(localId, mesaId)),
  comandos: (localId: string, mesaId: string): Comando[] => registros.get(clave(localId, mesaId))?.comandos ?? [],
  total: (): number => registros.size,
  /** Cambia cada vez que se modifica algún registro (para useSyncExternalStore). */
  version: (): number => version,
  /** Comandos aceptados en contingencia de todas las mesas de un local. */
  todos: (localId: string): Comando[] => [...registros.values()].filter((r) => r.localId === localId).flatMap((r) => r.comandos),
  /** Solo para pruebas. */
  limpiar(): void {
    registros.clear()
  },
  registrar(c: Comando): void {
    if (!c.mesaId) return
    const k = clave(c.localId, c.mesaId)
    const r = registros.get(k) ?? { localId: c.localId, mesaId: c.mesaId, pedidoId: null, comandos: [], desde: Date.now() }
    if (!r.comandos.some((x) => x.id === c.id)) r.comandos.push(c)
    r.pedidoId = typeof c.cuerpo.pedido_id === "string" ? c.cuerpo.pedido_id : r.pedidoId
    registros.set(k, r)
    avisar()
  },
  /** Una pasada: se llama cada 3 s mientras haya registros (ver useSondeo en LayoutOperacion). */
  async verificar(alAvisar: (mensaje: string) => void): Promise<void> {
    const porLocal = new Set([...registros.values()].map((r) => r.localId))
    for (const localId of porLocal) {
      let conflictos: Conflicto[] = []
      try {
        conflictos = (await leer<{ conflictos: Conflicto[] }>(`/locales/${localId}/caja/conflictos`)).conflictos
      } catch {
        /* garzón sin permiso de caja, o sin conexión: se decide solo con el pedido */
      }
      const rechazados = new Set(conflictos.map((x) => x.comando.command_id))
      for (const [k, r] of registros) {
        if (r.localId !== localId) continue
        r.comandos = r.comandos.filter((c) => !rechazados.has(c.id))
        let servidor: Pedido | null = null
        if (r.pedidoId) {
          try {
            servidor = await leer<Pedido>(`/locales/${localId}/pedidos/${r.pedidoId}`)
          } catch (e) {
            if (!(e instanceof ErrorApi && e.http === 404)) continue
          }
        }
        const superpuesto = r.comandos.reduce<Pedido | null>((p, c) => aplicar(p, c, "superponer"), servidor)
        if (r.comandos.length === 0 || huella(superpuesto) === huella(servidor)) {
          registros.delete(k)
        } else if (Date.now() - r.desde > ESPERA_MAXIMA_MS) {
          registros.delete(k)
          alAvisar(`La mesa ${r.mesaId} sigue sincronizando. Revisa la bandeja de conflictos.`)
        }
      }
    }
    avisar()
  },
}

let vaciando = false

/** Envía la cola local por contingencia, en orden. Devuelve cuántos se enviaron. */
export async function vaciarCola(localId: string): Promise<number> {
  if (vaciando || !tokenVigente()) return 0
  vaciando = true
  let enviados = 0
  try {
    let corte = false
    // Repite mientras queden comandas (una guardada durante el envío no espera al siguiente sondeo) y no haya corte.
    while (!corte) {
      const pendientes = await cola.pendientes(localId)
      if (pendientes.length === 0) break
      for (const g of pendientes) {
        try {
          await pedir("POST", "/contingencia/comandas", {
            cuerpo: { operacion: g.operacion, local_id: g.localId, cuerpo: g.cuerpo, ocurrido_en: g.creadoEn },
            commandId: g.id,
          })
          if (g.seq !== undefined) await cola.quitar(g.seq)
          sincronizacion.registrar(g)
          enviados++
        } catch (e) {
          if (e instanceof SesionRequerida || e instanceof SinConexion) {
            corte = true
            break
          }
          if (e instanceof ErrorApi && e.esFallaDeServicio) {
            corte = true
            break
          }
          if (e instanceof ErrorApi) {
            await cola.rechazar(g, e.codigo, e.message)
            continue
          }
          throw e
        }
      }
    }
  } finally {
    vaciando = false
  }
  return enviados
}
