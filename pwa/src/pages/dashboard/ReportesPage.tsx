import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { dia, turnos, type ResumenDia, type ResumenTurnoFila } from "@/api/reportes"
import { Aviso } from "@/components/comun/Aviso"
import { Tarjeta } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { mensajeDeError } from "@/hooks/useComando"
import { pesos } from "@/lib/dinero"
import { fechaHora, hoySantiago, restarDias } from "@/lib/fechas"
import { useSesion } from "@/sesion/useSesion"

export default function ReportesPage() {
  const { local } = useSesion()
  const localId = local!.local_id
  const hoy = hoySantiago()
  const [desde, setDesde] = useState(restarDias(hoy, 6))
  const [hasta, setHasta] = useState(hoy)
  const [lista, setLista] = useState<ResumenTurnoFila[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fecha, setFecha] = useState(hoy)
  const [resumenDia, setResumenDia] = useState<ResumenDia | null>(null)

  const buscar = useCallback(async () => {
    try {
      setLista((await turnos(localId, desde, hasta)).turnos)
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [localId, desde, hasta])

  useEffect(() => {
    void buscar()
  }, [buscar])

  async function verDia() {
    try {
      setResumenDia(await dia(localId, fecha))
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }

  const r = resumenDia?.resumen
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Reportes</h1>
      {error && <Aviso tipo="error">{error}</Aviso>}

      <Tarjeta titulo="Turnos">
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm"><span className="font-medium">Desde</span>
            <input type="date" className="block h-10 rounded-lg border px-3" value={desde} max={hasta} onChange={(e) => setDesde(e.target.value)} /></label>
          <label className="space-y-1 text-sm"><span className="font-medium">Hasta</span>
            <input type="date" className="block h-10 rounded-lg border px-3" value={hasta} min={desde} onChange={(e) => setHasta(e.target.value)} /></label>
        </div>
        {lista === null ? <p className="text-sm text-neutral-500">Cargando…</p> : lista.length === 0 ? <p className="text-sm text-neutral-500">No hay turnos en ese rango.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-neutral-500"><tr><th className="py-2">Fecha</th><th>Estado</th><th>Abierto</th><th className="text-right">Diferencia</th><th className="text-right">Ventas</th><th /></tr></thead>
              <tbody className="divide-y">
                {lista.map((t) => (
                  <tr key={t.turno_id}>
                    <td className="py-2">{t.fecha_operativa}</td>
                    <td>{t.estado === "abierto" ? "Abierto" : "Cerrado"}</td>
                    <td>{fechaHora(t.abierto_en)}</td>
                    <td className="text-right">{t.diferencia_efectivo === undefined ? "—" : pesos(t.diferencia_efectivo)}</td>
                    <td className="text-right">{t.total_ventas === undefined ? "—" : pesos(t.total_ventas)}</td>
                    <td className="text-right"><Link className="text-sm underline" to={`/l/${localId}/admin/reportes/turnos/${t.turno_id}`}>Ver detalle</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>

      <Tarjeta titulo="Resumen de un día">
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm"><span className="font-medium">Fecha</span>
            <input type="date" className="block h-10 rounded-lg border px-3" value={fecha} onChange={(e) => setFecha(e.target.value)} /></label>
          <Button type="button" className="h-10" onClick={() => void verDia()}>Ver resumen</Button>
        </div>
        {resumenDia && (
          <dl className="grid max-w-sm grid-cols-2 gap-1 text-sm">
            <dt>Ventas</dt><dd className="text-right">{r?.n_ventas ?? 0}</dd>
            <dt>Total vendido</dt><dd className="text-right">{pesos(r?.total_ventas ?? 0)}</dd>
            <dt>Propinas</dt><dd className="text-right">{pesos(r?.total_propinas ?? 0)}</dd>
            <dt>Cerradas sin venta</dt><dd className="text-right">{r?.n_cerrados_sin_venta ?? 0}</dd>
          </dl>
        )}
      </Tarjeta>
    </div>
  )
}
