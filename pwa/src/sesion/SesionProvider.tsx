import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react"
import { useParams } from "react-router-dom"
import { ErrorApi, SinConexion } from "@/api/cliente"
import { yo as pedirYo } from "@/api/salon"
import type { Yo } from "@/api/tipos"
import { estacionActiva, guardarSesionDeEstacion, sesionDeEstacion } from "@/offline/estacion"
import { red } from "@/offline/red"
import { SesionContexto, type ErrorAcceso, type ValorSesion } from "@/sesion/contexto"
import { cerrarSesion, estadoSesion, suscribirSesion } from "@/sesion/google"
import { localGuardado } from "@/sesion/localGuardado"

const CODIGOS_SIN_ACCESO = new Set(["USUARIO_NO_REGISTRADO", "USUARIO_ARCHIVADO", "EMAIL_NO_VERIFICADO"])

/** Va dentro del enrutador: lee el local de la URL (`/l/:localId`). */
export function SesionProvider({ children }: { children: ReactNode }) {
  const sesion = useSyncExternalStore(suscribirSesion, estadoSesion)
  const enLinea = useSyncExternalStore(red.suscribir, red.estado)
  const { localId: localDeLaUrl } = useParams()
  const [yoCargado, setYoCargado] = useState<Yo | null>(null)
  const [respaldo, setRespaldo] = useState<Yo | null>(null)
  const [respaldoBuscado, setRespaldoBuscado] = useState<string | null>(null)
  const [cargando, setCargando] = useState(false)
  const [errorAcceso, setErrorAcceso] = useState<ErrorAcceso | null>(null)
  const [errorCarga, setErrorCarga] = useState<string | null>(null)
  const [intento, setIntento] = useState(0)
  const pedido = useRef("")
  const [cerrada, setCerrada] = useState(false)

  const hayToken = sesion.token !== null
  const sub = sesion.sub

  useEffect(() => {
    if (hayToken) setCerrada(false)
  }, [hayToken])

  // Con token y sin /yo de esta persona: pedirlo.
  useEffect(() => {
    if (!hayToken) return
    const clave = `${sub}#${intento}`
    if (pedido.current === clave) return
    pedido.current = clave
    let vigente = true
    setCargando(true)
    setErrorCarga(null)
    pedirYo().then(
      async (datos) => {
        if (!vigente) return
        for (const local of datos.locales) {
          if (estacionActiva(local.local_id) !== null) {
            await guardarSesionDeEstacion(local.local_id, local, datos.sub, datos.nombre)
          }
        }
        if (!vigente) return
        setYoCargado(datos)
        setErrorAcceso(null)
        setCargando(false)
      },
      (e: unknown) => {
        if (!vigente) return
        setCargando(false)
        if (e instanceof ErrorApi && e.http === 403 && CODIGOS_SIN_ACCESO.has(e.codigo)) {
          setErrorAcceso({ codigo: e.codigo, mensaje: e.message })
        } else if (e instanceof ErrorApi && !e.esFallaDeServicio) {
          setErrorAcceso({ codigo: e.codigo, mensaje: e.message })
        } else if (e instanceof ErrorApi || e instanceof SinConexion) {
          setErrorCarga(e instanceof SinConexion ? "Sin conexión. Reintenta cuando vuelva internet." : e.message)
        }
      },
    )
    return () => {
      vigente = false
      pedido.current = ""
    }
  }, [hayToken, sub, intento])

  // Estación recargada sin token y sin internet: usar la última sesión guardada (P17).
  const localParaRespaldo = localDeLaUrl ?? localGuardado()
  useEffect(() => {
    if (hayToken || !localParaRespaldo || estacionActiva(localParaRespaldo) === null) return
    let vigente = true
    const buscado = localParaRespaldo
    sesionDeEstacion(buscado).then(
      (s) => {
        if (!vigente) return
        if (s) setRespaldo({ sub: s.sub, email: "", nombre: s.nombre, locales: [s.local] })
        setRespaldoBuscado(buscado)
      },
      () => vigente && setRespaldoBuscado(buscado),
    )
    return () => {
      vigente = false
    }
  }, [hayToken, localParaRespaldo])

  const reintentar = useCallback(() => {
    setErrorCarga(null)
    setIntento((n) => n + 1)
  }, [])

  const salir = useCallback(() => {
    cerrarSesion()
    setCerrada(true)
    setYoCargado(null)
    setRespaldo(null)
    setRespaldoBuscado(null)
    setErrorAcceso(null)
    setErrorCarga(null)
    setIntento(0)
  }, [])

  const valor = useMemo<ValorSesion>(() => {
    const buscandoRespaldo = !hayToken && !!localParaRespaldo && estacionActiva(localParaRespaldo) !== null && respaldoBuscado !== localParaRespaldo
    const sinConexionSoloLectura = !hayToken && yoCargado === null && respaldo !== null && enLinea === "sin_conexion"
    const propio = yoCargado !== null && (!hayToken || yoCargado.sub === sub) ? yoCargado : null
    const yo = sinConexionSoloLectura ? respaldo : propio
    const idLocal = localDeLaUrl ?? localGuardado()
    const local = yo?.locales.find((l) => l.local_id === idLocal) ?? (yo?.locales.length === 1 ? yo.locales[0] : null)
    return {
      sesion, yo, cargando: cargando || buscandoRespaldo, errorAcceso, errorCarga, local, rol: local?.rol ?? null,
      sinConexionSoloLectura, vencida: !hayToken && propio !== null, cerrada: cerrada && !hayToken, reintentar, salir,
    }
  }, [sesion, sub, cerrada, hayToken, yoCargado, respaldo, respaldoBuscado, localParaRespaldo, enLinea, cargando, errorAcceso, errorCarga, localDeLaUrl, reintentar, salir])

  return <SesionContexto.Provider value={valor}>{children}</SesionContexto.Provider>
}
