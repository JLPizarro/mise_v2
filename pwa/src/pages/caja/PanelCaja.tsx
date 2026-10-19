import { useCallback, useEffect, useState } from "react"
import { turnoActual } from "@/api/caja"
import type { Turno } from "@/api/tipos"
import CierreCaja from "@/components/caja/CierreCaja"
import ConflictosCaja from "@/components/caja/ConflictosCaja"
import DocumentosCaja from "@/components/caja/DocumentosCaja"
import EstacionCaja from "@/components/caja/EstacionCaja"
import ImpresionesRetenidas from "@/components/caja/ImpresionesRetenidas"
import PendientesCaja from "@/components/caja/PendientesCaja"
import RetirosCaja from "@/components/caja/RetirosCaja"
import { Aviso } from "@/components/comun/Aviso"
import { useEnLinea } from "@/hooks/useEnLinea"
import { mensajeDeError } from "@/hooks/useComando"
import { useSesion } from "@/sesion/useSesion"

const PESTANAS = ["Pendientes", "Turno", "Retiros", "Documentos", "Conflictos", "Impresiones retenidas", "Estación"] as const
type Pestana = (typeof PESTANAS)[number]

export default function PanelCaja() {
  const { local, sesion } = useSesion()
  const localId = local!.local_id
  const enLinea = useEnLinea()
  const hayToken = sesion.token !== null
  const [pestana, setPestana] = useState<Pestana>("Pendientes")
  const [turno, setTurno] = useState<Turno | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)

  const recargarTurno = useCallback(async () => {
    try {
      setTurno(await turnoActual(localId))
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [localId])

  useEffect(() => {
    if (hayToken) void recargarTurno()
  }, [recargarTurno, hayToken])

  const necesitaInternet = !enLinea && pestana !== "Estación"

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Caja</h1>
        <p className="text-sm text-neutral-600">
          {turno === undefined ? "Cargando turno…" : turno ? "Turno abierto" : "Sin turno abierto"}
        </p>
      </div>
      {error && <Aviso tipo="error">{error}</Aviso>}

      <div role="tablist" className="flex gap-2 overflow-x-auto pb-1">
        {PESTANAS.map((p) => (
          <button key={p} type="button" role="tab" aria-selected={pestana === p} onClick={() => setPestana(p)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium ${pestana === p ? "bg-neutral-950 text-white" : "border bg-white text-neutral-700"}`}>
            {p}
          </button>
        ))}
      </div>

      {necesitaInternet ? (
        <Aviso>Esta sección necesita internet</Aviso>
      ) : (
        <>
          {pestana === "Pendientes" && <PendientesCaja localId={localId} propinaPct={local!.propina_sugerida_pct} irATurno={() => setPestana("Turno")} />}
          {pestana === "Turno" && turno !== undefined && <CierreCaja localId={localId} turno={turno} onCambio={() => void recargarTurno()} />}
          {pestana === "Retiros" && <RetirosCaja localId={localId} />}
          {pestana === "Documentos" && <DocumentosCaja localId={localId} />}
          {pestana === "Conflictos" && <ConflictosCaja localId={localId} />}
          {pestana === "Impresiones retenidas" && <ImpresionesRetenidas localId={localId} />}
          {pestana === "Estación" && <EstacionCaja localId={localId} />}
        </>
      )}
    </section>
  )
}
