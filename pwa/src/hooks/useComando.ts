import { useCallback, useEffect, useRef } from "react"
import { ErrorApi, SesionRequerida, SinConexion } from "@/api/cliente"
import { ejecutar, type Comando, type Resultado } from "@/api/comandos"
import { useNotificar } from "@/components/comun/avisos"
import { useSesion } from "@/sesion/useSesion"

type Fin = (resultado: Resultado<unknown>) => void | Promise<void>
/** Se llama con el error antes de avisar. Si devuelve true, la pantalla ya lo mostró y no se muestra el aviso. */
type AlError = (e: unknown) => boolean | void

export function mensajeDeError(e: unknown): string {
  if (e instanceof ErrorApi || e instanceof SinConexion || e instanceof Error) return e.message
  return "No se pudo completar la acción."
}

/**
 * Ejecuta comandos con los avisos de la interfaz (7.1):
 *  - contingencia: «Registrada en contingencia…» (y, si fue enviar_tanda, «No se imprimió…»);
 *  - cola local: «Guardada en este equipo…»;
 *  - sesión vencida: guarda el MISMO comando en memoria y lo reintenta con el mismo ID cuando
 *    la persona vuelve a ingresar.
 * Devuelve el resultado, o null si falló (el aviso de error ya se mostró).
 */
export function useComando() {
  const notificar = useNotificar()
  const { sesion } = useSesion()
  const hayToken = sesion.token !== null
  const enEspera = useRef<{ c: Comando; fin?: Fin; alError?: AlError } | null>(null)

  const correr = useCallback(
    async <T>(c: Comando, fin?: (r: Resultado<T>) => void | Promise<void>, alError?: AlError): Promise<Resultado<T> | null> => {
      try {
        const resultado = await ejecutar<T>(c)
        if (resultado.via === "contingencia") {
          notificar(
            "Registrada en contingencia: se aplicará en unos segundos." +
              (c.operacion === "pedido.enviar_tanda" ? " No se imprimió: la caja decide si imprimir." : ""),
            "info",
          )
        } else if (resultado.via === "cola_local") {
          notificar("Guardada en este equipo. Se enviará cuando vuelva internet.", "info")
        }
        await fin?.(resultado)
        return resultado
      } catch (e) {
        if (e instanceof SesionRequerida) {
          enEspera.current = { c, fin: fin as Fin | undefined, alError }
          notificar("Ingresa de nuevo para continuar. Tu acción se reintentará al ingresar.", "info")
        } else if (!alError?.(e)) {
          notificar(mensajeDeError(e), "error")
        }
        return null
      }
    },
    [notificar],
  )

  // Al volver la sesión, el comando pendiente se reintenta con el mismo ID.
  useEffect(() => {
    if (!hayToken || !enEspera.current) return
    const { c, fin, alError } = enEspera.current
    enEspera.current = null
    void correr(c, fin, alError)
  }, [hayToken, correr])

  return correr
}

/**
 * Para escrituras que no son de comanda (caja, salón, administración): solo hay vía normal.
 * Devuelve los datos de la respuesta, o null si falló. `alError` puede mostrar el error a su manera.
 */
export function useEscribir() {
  const correr = useComando()
  return useCallback(
    async <T>(c: Comando, fin?: (datos: T) => void | Promise<void>, alError?: AlError): Promise<T | null> => {
      const guardado: { datos: T | null } = { datos: null }
      await correr<T>(
        c,
        async (r) => {
          if (r.via !== "normal") return
          guardado.datos = r.respuesta.datos
          await fin?.(r.respuesta.datos)
        },
        alError,
      )
      return guardado.datos
    },
    [correr],
  )
}
