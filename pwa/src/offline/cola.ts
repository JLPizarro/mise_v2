import type { Comando } from "@/api/comandos"
import { db, type Guardado, type Rechazado } from "@/offline/db"
import { estadoSesion } from "@/sesion/google"
import { sesionDeEstacion } from "@/offline/estacion"

const oyentes = new Set<() => void>()
const avisar = () => oyentes.forEach((o) => o())

export const cola = {
  suscribir(oyente: () => void): () => void {
    oyentes.add(oyente)
    return () => { oyentes.delete(oyente) }
  },
  async agregar(c: Comando): Promise<void> {
    const sesion = estadoSesion()
    const respaldo = await sesionDeEstacion(c.localId)
    const registradoPor = sesion.sub ? { sub: sesion.sub, nombre: sesion.nombre } : { sub: respaldo?.sub ?? "", nombre: respaldo?.nombre ?? "" }
    try {
      await (await db()).add("comandos", { ...c, registradoPor })
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "ConstraintError")) throw e // mismo ID: ya estaba en la cola
    }
    avisar()
  },
  async pendientes(localId: string): Promise<Guardado[]> {
    const todos = await (await db()).getAllFromIndex("comandos", "porLocal", localId)
    return todos.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0))
  },
  async contar(localId: string): Promise<number> {
    return (await db()).countFromIndex("comandos", "porLocal", localId)
  },
  async quitar(seq: number): Promise<void> {
    await (await db()).delete("comandos", seq)
    avisar()
  },
  async rechazar(g: Guardado, codigo: string, mensaje: string): Promise<void> {
    const base = await db()
    const registro: Rechazado = { ...g, codigo, mensaje, rechazadoEn: new Date().toISOString() }
    delete registro.seq
    await base.put("rechazados", registro)
    if (g.seq !== undefined) await base.delete("comandos", g.seq)
    avisar()
  },
  async rechazados(localId: string): Promise<Rechazado[]> {
    return (await (await db()).getAll("rechazados")).filter((r) => r.localId === localId)
  },
  async descartarRechazado(id: string): Promise<void> {
    await (await db()).delete("rechazados", id)
    avisar()
  },
}
