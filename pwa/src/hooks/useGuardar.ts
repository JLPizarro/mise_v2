import { useCallback, useState } from "react"
import type { Comando } from "@/api/comandos"
import { mensajeDeError, useEscribir } from "@/hooks/useComando"

/** Guarda desde un formulario: el error del servidor se queda en el formulario (sin aviso aparte). */
export function useGuardar() {
  const escribir = useEscribir()
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const guardar = useCallback(
    async <T,>(c: Comando, alOk?: (datos: T) => void | Promise<void>): Promise<T | null> => {
      setGuardando(true)
      setError(null)
      try {
        return await escribir<T>(c, alOk, (e) => {
          setError(mensajeDeError(e))
          return true
        })
      } finally {
        setGuardando(false)
      }
    },
    [escribir],
  )

  return { guardando, error, guardar, limpiarError: () => setError(null) }
}
