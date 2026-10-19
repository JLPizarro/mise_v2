import { openDB, type DBSchema, type IDBPDatabase } from "idb"
import type { Comando } from "@/api/comandos"

export interface Guardado extends Comando { seq?: number; registradoPor: { sub: string; nombre: string } }
export interface Rechazado extends Guardado { codigo: string; mensaje: string; rechazadoEn: string }
export interface EntradaCache { clave: string; valor: unknown; guardadoEn: number }

interface EsquemaPos extends DBSchema {
  comandos: { key: number; value: Guardado; indexes: { porLocal: string; porId: string } }
  rechazados: { key: string; value: Rechazado }
  cache: { key: string; value: EntradaCache }
}

let conexion: Promise<IDBPDatabase<EsquemaPos>> | null = null
export function db(): Promise<IDBPDatabase<EsquemaPos>> {
  conexion ??= openDB<EsquemaPos>("pos-caja", 1, {
    upgrade(base) {
      const comandos = base.createObjectStore("comandos", { keyPath: "seq", autoIncrement: true })
      comandos.createIndex("porLocal", "localId")
      comandos.createIndex("porId", "id", { unique: true })
      base.createObjectStore("rechazados", { keyPath: "id" })
      base.createObjectStore("cache", { keyPath: "clave" })
    },
  })
  return conexion
}
