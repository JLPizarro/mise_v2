export interface Config {
  api_url: string
  google_client_id: string
  modo_dev: boolean
}

let actual: Config | null = null

export async function cargarConfig(): Promise<Config> {
  const respuesta = await fetch("./config.json", { cache: "no-store" })
  if (!respuesta.ok) throw new Error("No se encontró config.json")
  const datos = (await respuesta.json()) as Partial<Config>
  actual = {
    api_url: String(datos.api_url ?? "").replace(/\/+$/, ""),
    google_client_id: String(datos.google_client_id ?? ""),
    modo_dev: datos.modo_dev === true,
  }
  return actual
}

export function config(): Config {
  if (!actual) throw new Error("La configuración no está cargada")
  return actual
}

/** Solo para pruebas. */
export function fijarConfig(valor: Config): void {
  actual = valor
}
