import { vi } from "vitest"
import { fijarConfig } from "@/config"
import { db } from "@/offline/db"
import { red } from "@/offline/red"
import { sincronizacion } from "@/offline/sincronizar"
import { cerrarSesion, ingresarDev } from "@/sesion/google"

export const API = "http://api.test"

export function respuesta(status: number, cuerpo: unknown = {}, cabeceras: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "content-type": "application/json", ...cabeceras } })
}

type Paso = Response | Error | (() => Response)

/** Reemplaza fetch. Cada llamada consume un paso; el último se repite si es función o error. */
export function simularFetch(...pasos: Paso[]) {
  const restantes = [...pasos]
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => {
    const paso = restantes.length > 1 ? restantes.shift()! : restantes[0]
    if (paso instanceof Error) throw paso
    return typeof paso === "function" ? paso() : paso
  })
  vi.stubGlobal("fetch", mock)
  return mock
}

export const rutasLlamadas = (mock: ReturnType<typeof simularFetch>): string[] =>
  mock.mock.calls.map(([url]) => String(url).replace(API, ""))

export const cabecera = (mock: ReturnType<typeof simularFetch>, n: number, nombre: string): string | undefined =>
  (mock.mock.calls[n][1]?.headers as Record<string, string> | undefined)?.[nombre]

export const cuerpoEnviado = (mock: ReturnType<typeof simularFetch>, n: number): Record<string, unknown> =>
  JSON.parse(String(mock.mock.calls[n][1]?.body)) as Record<string, unknown>

export async function prepararEntorno(sub = "mock-cajero"): Promise<void> {
  vi.unstubAllGlobals()
  fijarConfig({ api_url: API, google_client_id: "", modo_dev: true })
  localStorage.clear()
  const base = await db()
  await base.clear("comandos")
  await base.clear("rechazados")
  await base.clear("cache")
  sincronizacion.limpiar()
  red.reportarRespuesta()
  cerrarSesion()
  ingresarDev(sub)
}
