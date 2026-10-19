import { useEffect, useMemo, useState, useSyncExternalStore } from "react"
import type { Comando } from "@/api/comandos"
import { cola } from "@/offline/cola"
import { estacionActiva } from "@/offline/estacion"
import { sincronizacion } from "@/offline/sincronizar"

/**
 * Comandos de un local que aún no están reflejados en el servidor: los guardados en este equipo
 * (cola local) y los aceptados en contingencia que se están sincronizando. Primero van los de la
 * cola local: son los más nuevos.
 */
export function useComandosPendientes(localId: string): Comando[] {
  const [enCola, setEnCola] = useState<Comando[]>([])
  const versionSync = useSyncExternalStore(sincronizacion.suscribir, sincronizacion.version)

  useEffect(() => {
    if (estacionActiva(localId) === null) return // los celulares no guardan comandas
    let vigente = true
    const leer = () => void cola.pendientes(localId).then((p) => vigente && setEnCola(p))
    leer()
    const baja = cola.suscribir(leer)
    return () => {
      vigente = false
      baja()
    }
  }, [localId])

  // El arreglo solo cambia cuando cambia la cola o la sincronización (versionSync).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => [...sincronizacion.todos(localId), ...enCola], [localId, enCola, versionSync])
}

/** Etiqueta de una mesa con comandos sin confirmar: «Sincronizando» o «Guardada en este equipo». */
export function etiquetaPendiente(localId: string, mesaId: string, pendientes: Comando[]): "Sincronizando" | "Guardada en este equipo" | null {
  if (sincronizacion.activa(localId, mesaId)) return "Sincronizando"
  return pendientes.some((c) => c.mesaId === mesaId) ? "Guardada en este equipo" : null
}
