import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { turnoActual } from "@/api/caja"
import type { Turno } from "@/api/tipos"
import { dia, type ResumenDia } from "@/api/reportes"
import { Aviso } from "@/components/comun/Aviso"
import { Tarjeta } from "@/components/dashboard/ui"
import { mensajeDeError } from "@/hooks/useComando"
import { pesos } from "@/lib/dinero"
import { fechaHora, hoySantiago } from "@/lib/fechas"
import { useSesion } from "@/sesion/useSesion"

const ACCESOS = [
  ["catalogo", "Catálogo", "Productos, precios y modificadores"],
  ["salon", "Salón y cocina", "Sectores, mesas, cuartos e impresoras"],
  ["inventario", "Inventario", "Materias primas y recetas"],
  ["personal", "Personal", "Personas, roles e invitaciones"],
  ["configuracion", "Configuración", "Local, estaciones y código de autorización"],
  ["reportes", "Reportes", "Turnos y resumen por día"],
] as const

export default function DashboardPage() {
  const { local } = useSesion()
  const localId = local!.local_id
  const [turno, setTurno] = useState<Turno | null | undefined>(undefined)
  const [resumen, setResumen] = useState<ResumenDia | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    turnoActual(localId).then(setTurno, (e: unknown) => setError(mensajeDeError(e)))
    dia(localId, hoySantiago()).then(setResumen, () => setResumen(null))
  }, [localId])

  const r = resumen?.resumen
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Inicio</h1>
      {error && <Aviso tipo="error">{error}</Aviso>}
      <div className="grid gap-4 md:grid-cols-2">
        <Tarjeta titulo="Turno actual">
          {turno === undefined ? <p className="text-sm text-neutral-500">Cargando…</p>
            : turno === null ? <p className="text-sm text-neutral-600">Sin turno abierto.</p>
            : <p className="text-sm">Abierto desde {fechaHora(turno.abierto_en)} · apertura {pesos(turno.monto_apertura)}</p>}
        </Tarjeta>
        <Tarjeta titulo={`Resumen de hoy (${hoySantiago()})`}>
          <dl className="grid grid-cols-2 gap-1 text-sm">
            <dt>Ventas</dt><dd className="text-right">{r?.n_ventas ?? 0}</dd>
            <dt>Total vendido</dt><dd className="text-right">{pesos(r?.total_ventas ?? 0)}</dd>
            <dt>Propinas</dt><dd className="text-right">{pesos(r?.total_propinas ?? 0)}</dd>
            <dt>Mesas cerradas sin venta</dt><dd className="text-right">{r?.n_cerrados_sin_venta ?? 0}</dd>
          </dl>
        </Tarjeta>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ACCESOS.map(([ruta, nombre, descripcion]) => (
          <Link key={ruta} to={`/l/${localId}/admin/${ruta}`} className="rounded-2xl border bg-white p-4 transition hover:shadow-md">
            <p className="font-semibold">{nombre}</p>
            <p className="text-sm text-neutral-500">{descripcion}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
