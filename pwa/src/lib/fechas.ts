const ZONA = "America/Santiago"
const HORA = new Intl.DateTimeFormat("es-CL", { timeZone: ZONA, hour: "2-digit", minute: "2-digit" })
const FECHA_HORA = new Intl.DateTimeFormat("es-CL", {
  timeZone: ZONA, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
})
const DIA = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA })

export const hora = (iso: string): string => HORA.format(new Date(iso))
export const fechaHora = (iso: string): string => FECHA_HORA.format(new Date(iso))
/** Hoy en Santiago, como AAAA-MM-DD. */
export const hoySantiago = (): string => DIA.format(new Date())

/** Resta días a una fecha AAAA-MM-DD (en UTC, sin horas: sirve para rangos de reportes). */
export function restarDias(fecha: string, dias: number): string {
  const [a, m, d] = fecha.split("-").map(Number)
  return new Date(Date.UTC(a, m - 1, d - dias)).toISOString().slice(0, 10)
}
