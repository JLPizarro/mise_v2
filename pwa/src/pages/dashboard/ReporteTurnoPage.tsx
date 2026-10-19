import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { turno as pedirTurno, type DetalleTurno } from "@/api/reportes"
import { Aviso } from "@/components/comun/Aviso"
import { Tarjeta } from "@/components/dashboard/ui"
import { mensajeDeError } from "@/hooks/useComando"
import { pesos } from "@/lib/dinero"
import { fechaHora } from "@/lib/fechas"
import { useSesion } from "@/sesion/useSesion"

const ETIQUETA_DOC: Record<string, string> = { pendiente: "Pendientes", enviando: "Emitiendo", emitido: "Emitidos", rechazado: "Rechazados", fallido: "Fallidos" }

export default function ReporteTurnoPage() {
  const { local } = useSesion()
  const localId = local!.local_id
  const turnoId = useParams().turnoId!
  const [datos, setDatos] = useState<DetalleTurno | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    pedirTurno(localId, turnoId).then(setDatos, (e: unknown) => setError(mensajeDeError(e)))
  }, [localId, turnoId])

  if (error) return <Aviso tipo="error">{error}</Aviso>
  if (!datos) return <p className="text-sm text-neutral-500">Cargando…</p>
  const { turno, caja, resumen, por_garzon, retiros, documentos } = datos

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/l/${localId}/admin/reportes`} className="text-sm underline">← Reportes</Link>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Turno del {turno.fecha_operativa}</h1>
        <p className="text-sm text-neutral-600">
          {turno.estado === "abierto" ? "Abierto" : "Cerrado"} · desde {fechaHora(turno.abierto_en)}{turno.cerrado_en && ` hasta ${fechaHora(turno.cerrado_en)}`}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Tarjeta titulo="Caja">
          <dl className="grid grid-cols-2 gap-1 text-sm">
            <dt>Efectivo</dt><dd className="text-right">{pesos(caja.efectivo)}</dd>
            <dt>Débito</dt><dd className="text-right">{pesos(caja.debito)}</dd>
            <dt>Crédito</dt><dd className="text-right">{pesos(caja.credito)}</dd>
            <dt>Transferencia</dt><dd className="text-right">{pesos(caja.transferencia)}</dd>
            <dt>Retiros</dt><dd className="text-right">{pesos(caja.retiros)}</dd>
            <dt>Pagos</dt><dd className="text-right">{caja.n_pagos}</dd>
            {turno.efectivo_esperado !== undefined && <><dt>Efectivo esperado</dt><dd className="text-right">{pesos(turno.efectivo_esperado)}</dd></>}
            {turno.resultado && <><dt className="font-medium">Diferencia de efectivo</dt><dd className="text-right font-medium">{pesos(turno.resultado.diferencia_efectivo)}</dd></>}
          </dl>
        </Tarjeta>
        <Tarjeta titulo="Resumen">
          <dl className="grid grid-cols-2 gap-1 text-sm">
            <dt>Ventas</dt><dd className="text-right">{resumen.n_ventas ?? caja.n_ventas}</dd>
            <dt>Total vendido</dt><dd className="text-right">{pesos(resumen.total_ventas ?? caja.total_ventas)}</dd>
            <dt>Propinas</dt><dd className="text-right">{pesos(resumen.total_propinas ?? 0)}</dd>
            <dt>Retiros</dt><dd className="text-right">{resumen.n_retiros ?? 0} · {pesos(resumen.total_retiros ?? 0)}</dd>
          </dl>
        </Tarjeta>
      </div>

      <Tarjeta titulo="Ventas por garzón">
        {por_garzon.length === 0 ? <p className="text-sm text-neutral-500">Sin ventas.</p> : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-neutral-500"><tr><th className="py-2">Garzón</th><th className="text-right">Ventas</th><th className="text-right">Total</th><th className="text-right">Propinas</th></tr></thead>
            <tbody className="divide-y">
              {por_garzon.map((g) => (
                <tr key={g.garzon_id}><td className="py-2">{g.garzon_id}</td><td className="text-right">{g.n_ventas}</td><td className="text-right">{pesos(g.total_ventas)}</td><td className="text-right">{pesos(g.total_propinas)}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Tarjeta>

      <div className="grid gap-4 md:grid-cols-2">
        <Tarjeta titulo="Retiros">
          {retiros.length === 0 ? <p className="text-sm text-neutral-500">Sin retiros.</p> : (
            <ul className="divide-y text-sm">{retiros.map((r) => <li key={r.retiro_id} className="flex justify-between py-2"><span>{r.motivo}</span><span>{pesos(r.monto)}</span></li>)}</ul>
          )}
        </Tarjeta>
        <Tarjeta titulo="Documentos por estado">
          {Object.keys(documentos).length === 0 ? <p className="text-sm text-neutral-500">Sin documentos.</p> : (
            <ul className="divide-y text-sm">{Object.entries(documentos).map(([estado, n]) => <li key={estado} className="flex justify-between py-2"><span>{ETIQUETA_DOC[estado] ?? estado}</span><span>{n}</span></li>)}</ul>
          )}
        </Tarjeta>
      </div>
    </div>
  )
}
