import { useCallback, useEffect, useState } from "react"
import { descartarImpresion, impresionesRetenidas, liberarImpresion } from "@/api/caja"
import type { TrabajoRetenido } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import { Button } from "@/components/ui/button"
import { mensajeDeError, useEscribir } from "@/hooks/useComando"
import { hora } from "@/lib/fechas"

/** Comandas que llegaron por contingencia: la cocina ya las atendió en papel, así que la caja decide si imprimir. */
export default function ImpresionesRetenidas({ localId }: { localId: string }) {
  const escribir = useEscribir()
  const notificar = useNotificar()
  const [lista, setLista] = useState<TrabajoRetenido[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setLista((await impresionesRetenidas(localId)).trabajos)
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [localId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div className="space-y-3">
      {error && <Aviso tipo="error">{error}</Aviso>}
      {lista === null && !error && <p className="text-sm text-neutral-500">Cargando…</p>}
      {lista?.length === 0 && <p className="text-sm text-neutral-500">No hay impresiones retenidas.</p>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {lista?.map((t) => (
          <li key={t.trabajo_id} className="space-y-2 rounded-2xl border bg-white p-4 text-sm">
            <p className="font-semibold">Mesa {t.mesa_numero ?? t.mesa_id} · {t.cuarto}</p>
            <p className="text-xs text-neutral-500">{t.garzon} · {hora(t.creado_en)}{t.sector ? ` · ${t.sector}` : ""}</p>
            <ul className="space-y-0.5">
              {t.lineas.map((l, i) => (
                <li key={i}>{l.cantidad} × {l.nombre}{l.modificador && ` (${l.modificador})`}{l.observacion && <span className="text-neutral-500"> — {l.observacion}</span>}</li>
              ))}
            </ul>
            <div className="flex gap-2 pt-1">
              <Button type="button" size="sm"
                onClick={() => void escribir(liberarImpresion(localId, t.trabajo_id), () => { notificar("Enviada a la impresora", "ok"); void cargar() })}>
                Imprimir ahora
              </Button>
              <Button type="button" size="sm" variant="outline"
                onClick={() => void escribir(descartarImpresion(localId, t.trabajo_id), () => void cargar())}>
                Descartar
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
