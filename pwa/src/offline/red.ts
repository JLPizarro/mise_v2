import { config } from "@/config"

type EstadoRed = "en_linea" | "sin_conexion"
let estado: EstadoRed = navigator.onLine ? "en_linea" : "sin_conexion"
const oyentes = new Set<() => void>()
let sondeo: number | undefined

function cambiar(nuevo: EstadoRed): void {
  if (nuevo === estado) return
  estado = nuevo
  if (nuevo === "sin_conexion" && sondeo === undefined) sondeo = window.setInterval(() => void sondear(), 10_000)
  if (nuevo === "en_linea" && sondeo !== undefined) { window.clearInterval(sondeo); sondeo = undefined }
  oyentes.forEach((o) => o())
}

/** Vuelve "en línea" solo si /salud responde 200 (la API y DynamoDB responden). */
async function sondear(): Promise<void> {
  try {
    const r = await fetch(`${config().api_url}/salud`, { cache: "no-store", signal: AbortSignal.timeout(5000) })
    if (r.status === 200) cambiar("en_linea")
  } catch {
    /* sigue sin conexión */
  }
}

window.addEventListener("offline", () => cambiar("sin_conexion"))
window.addEventListener("online", () => void sondear())

export const red = {
  estado: (): EstadoRed => estado,
  sinConexion: (): boolean => estado === "sin_conexion",
  suscribir(oyente: () => void): () => void {
    oyentes.add(oyente)
    return () => { oyentes.delete(oyente) }
  },
  reportarFalla: (): void => cambiar("sin_conexion"),
  reportarRespuesta: (): void => cambiar("en_linea"),
  sondear,
}
