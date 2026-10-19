import { config } from "@/config"

export interface EstadoSesion { token: string | null; expira: number; sub: string; nombre: string; email: string }

const VACIA: EstadoSesion = { token: null, expira: 0, sub: "", nombre: "", email: "" }
let estado: EstadoSesion = VACIA
const oyentes = new Set<() => void>()
let renovacion: number | undefined
let vencimiento: number | undefined
let cargando: Promise<void> | null = null

export function suscribirSesion(oyente: () => void): () => void {
  oyentes.add(oyente)
  return () => { oyentes.delete(oyente) }
}
export const estadoSesion = (): EstadoSesion => estado
const emitir = () => oyentes.forEach((o) => o())

/** El token, si le queda más de un minuto. Nunca se guarda fuera de esta variable. */
export function tokenVigente(): string | null {
  return estado.token && Date.now() < estado.expira - 60_000 ? estado.token : null
}

export function sesionVencida(): void {
  estado = { ...estado, token: null, expira: 0 }
  emitir()
}

function leerPayload(jwt: string): Record<string, unknown> {
  const parte = jwt.split(".")[1] ?? ""
  const base64 = parte.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(parte.length / 4) * 4, "=")
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
  return JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>
}

function recibirCredencial(jwt: string): void {
  const p = leerPayload(jwt)
  estado = { token: jwt, expira: Number(p.exp) * 1000, sub: String(p.sub ?? ""), nombre: String(p.name ?? ""), email: String(p.email ?? "") }
  window.clearTimeout(renovacion)
  window.clearTimeout(vencimiento)
  vencimiento = window.setTimeout(sesionVencida, Math.max(0, estado.expira - Date.now() - 60_000))
  renovacion = window.setTimeout(() => window.google?.accounts.id.prompt(), Math.max(0, estado.expira - Date.now() - 5 * 60_000))
  emitir()
}

export function cargarGoogle(autoSeleccion: boolean): Promise<void> {
  if (cargando) return cargando
  cargando = new Promise<void>((resolver, rechazar) => {
    const script = document.createElement("script")
    script.src = "https://accounts.google.com/gsi/client"
    script.async = true
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: config().google_client_id,
        callback: (r: { credential: string }) => recibirCredencial(r.credential),
        auto_select: autoSeleccion,
        use_fedcm_for_prompt: true,
        cancel_on_tap_outside: false,
      })
      resolver()
    }
    script.onerror = () => {
      cargando = null
      rechazar(new Error("No se pudo cargar el inicio de sesión de Google"))
    }
    document.head.appendChild(script)
  })
  return cargando
}

export const dibujarBotonGoogle = (elemento: HTMLElement): void =>
  window.google?.accounts.id.renderButton(elemento, { theme: "outline", size: "large", locale: "es", text: "signin_with" })

export const intentarIngresoSilencioso = (): void => window.google?.accounts.id.prompt()

export function ingresarDev(sub: string, duracionMs = 12 * 3600_000): void {
  if (!config().modo_dev) throw new Error("El ingreso de desarrollo está desactivado")
  estado = { token: `dev:${sub}`, expira: Date.now() + duracionMs, sub, nombre: sub, email: `${sub}@demo.invalid` }
  emitir()
}

export function cerrarSesion(): void {
  window.clearTimeout(renovacion)
  window.clearTimeout(vencimiento)
  window.google?.accounts.id.disableAutoSelect()
  estado = VACIA
  emitir()
}
