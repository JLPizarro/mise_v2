import { useCallback, useEffect, useMemo, useState } from "react"
import { pendientes as pedirPendientes } from "@/api/caja"
import type { Pedido } from "@/api/tipos"
import CobroMesa from "@/components/caja/CobroMesa"
import TarjetaMesaCobro from "@/components/caja/TarjetaMesaCobro"
import { Aviso } from "@/components/comun/Aviso"
import { mensajeDeError } from "@/hooks/useComando"
import { usePlano } from "@/hooks/usePlano"
import { useSondeo } from "@/hooks/useSondeo"

interface Props { localId: string; propinaPct: number; irATurno: () => void }

/** Mesas en precuenta esperando cobro. Se actualiza cada 10 s. */
export default function PendientesCaja({ localId, propinaPct, irATurno }: Props) {
  const { plano } = usePlano(localId)
  const [lista, setLista] = useState<{ mesa_id: string; pedido: Pedido }[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cobrando, setCobrando] = useState<{ mesa_id: string; pedido: Pedido } | null>(null)

  const cargar = useCallback(async () => {
    try {
      setLista((await pedirPendientes(localId)).pendientes)
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [localId])

  useEffect(() => {
    void cargar()
  }, [cargar])
  useSondeo(cargar, 10_000, cobrando === null)

  const mesas = useMemo(() => new Map((plano?.mesas ?? []).map((m) => [m.mesa_id, m])), [plano])

  return (
    <section className="space-y-4">
      {error && <Aviso tipo="error">{error}</Aviso>}
      {lista === null && !error && <p className="text-sm text-neutral-500">Cargando…</p>}
      {lista?.length === 0 && <p className="text-sm text-neutral-500">No hay mesas esperando cobro.</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {lista?.map((p) => (
          <TarjetaMesaCobro key={p.pedido.pedido_id} numero={mesas.get(p.mesa_id)?.numero ?? null}
            sector={mesas.get(p.mesa_id)?.sector_nombre ?? null} pedido={p.pedido} onCobrar={() => setCobrando(p)} />
        ))}
      </div>
      {cobrando && (
        <CobroMesa
          key={cobrando.pedido.pedido_id}
          localId={localId}
          pedidoInicial={cobrando.pedido}
          numeroMesa={mesas.get(cobrando.mesa_id)?.numero ?? null}
          propinaPct={propinaPct}
          onCerrar={() => {
            setCobrando(null)
            void cargar()
          }}
          onActualizado={() => void cargar()}
          irATurno={irATurno}
        />
      )}
    </section>
  )
}
