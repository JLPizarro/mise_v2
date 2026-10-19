import { config } from "@/config"
import { red } from "@/offline/red"
import { estadoSesion, sesionVencida, tokenVigente } from "@/sesion/google"

export class ErrorApi extends Error {
  readonly http: number
  readonly codigo: string
  readonly detalle: Record<string, unknown>
  readonly requestId: string
  constructor(http: number, codigo: string, mensaje: string, detalle: Record<string, unknown> = {}, requestId = "") {
    super(mensaje)
    this.name = "ErrorApi"
    this.http = http
    this.codigo = codigo
    this.detalle = detalle
    this.requestId = requestId
  }
  get esFallaDeServicio(): boolean {
    return this.http >= 500 || this.http === 429
  }
}

export class SinConexion extends Error {
  constructor(mensaje = "Sin conexión") {
    super(mensaje)
    this.name = "SinConexion"
  }
}

export class SesionRequerida extends Error {
  constructor() {
    super("Ingresa de nuevo para continuar")
    this.name = "SesionRequerida"
  }
}

export type Metodo = "GET" | "POST" | "PATCH" | "DELETE"
export interface Respuesta<T> { http: number; datos: T; repetido: boolean }
interface Opciones {
  cuerpo?: unknown
  commandId?: string
  query?: Record<string, string | undefined>
  publica?: boolean
  timeoutMs?: number
}

export const TIEMPO_MAXIMO_MS = 8000

export async function pedir<T>(metodo: Metodo, ruta: string, op: Opciones = {}): Promise<Respuesta<T>> {
  const token = op.publica ? null : tokenVigente()
  if (!op.publica && !token) {
    // Queda token en memoria pero ya no es vigente (último minuto): se marca vencida para que la pantalla pida ingresar.
    if (estadoSesion().token !== null) sesionVencida()
    throw new SesionRequerida()
  }
  const params = new URLSearchParams()
  for (const [clave, valor] of Object.entries(op.query ?? {})) if (valor !== undefined) params.set(clave, valor)
  const qs = params.toString()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (op.commandId) headers["X-Command-Id"] = op.commandId
  if (op.cuerpo !== undefined) headers["Content-Type"] = "application/json"

  const control = new AbortController()
  const temporizador = window.setTimeout(() => control.abort(), op.timeoutMs ?? TIEMPO_MAXIMO_MS)
  let r: Response
  try {
    r = await fetch(`${config().api_url}${ruta}${qs ? `?${qs}` : ""}`, {
      method: metodo,
      headers,
      body: op.cuerpo === undefined ? undefined : JSON.stringify(op.cuerpo),
      signal: control.signal,
      cache: "no-store",
    })
  } catch {
    red.reportarFalla()
    throw new SinConexion()
  } finally {
    window.clearTimeout(temporizador)
  }
  red.reportarRespuesta()

  const esJson = (r.headers.get("content-type") ?? "").includes("application/json")
  const datos: unknown = esJson ? await r.json().catch(() => ({})) : await r.text()
  if (r.status === 401) {
    sesionVencida()
    throw new SesionRequerida()
  }
  if (!r.ok) {
    const d = (typeof datos === "object" && datos !== null ? datos : {}) as Record<string, unknown>
    const generico = r.status >= 500 || r.status === 429
      ? "El servicio no está disponible en este momento. Intenta de nuevo."
      : "No se pudo completar la acción."
    throw new ErrorApi(r.status, String(d.codigo ?? `HTTP_${r.status}`), String(d.mensaje ?? generico),
      (d.detalle as Record<string, unknown> | undefined) ?? {}, String(d.requestId ?? ""))
  }
  return { http: r.status, datos: datos as T, repetido: r.headers.get("x-comando-repetido") === "true" }
}

export async function leer<T>(ruta: string, query?: Record<string, string | undefined>): Promise<T> {
  return (await pedir<T>("GET", ruta, { query })).datos
}
