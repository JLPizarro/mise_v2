import { useCallback, useEffect, useState } from "react"
import { listar, type Recurso } from "@/api/admin"
import { mensajeDeError } from "@/hooks/useComando"

/** Lista de un recurso de administración: `GET L/admin/{recurso}` → `{[recurso]: T[]}`. */
export function useAdminLista<T>(localId: string, recurso: Recurso) {
  const [datos, setDatos] = useState<T[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const recargar = useCallback(async () => {
    try {
      setDatos((await listar<Record<string, T[]>>(localId, recurso))[recurso])
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [localId, recurso])

  useEffect(() => {
    void recargar()
  }, [recargar])

  return { datos, error, recargar }
}
