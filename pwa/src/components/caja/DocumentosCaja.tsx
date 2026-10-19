import { useCallback, useEffect, useState } from "react"
import { documentos as pedirDocumentos, reimprimir } from "@/api/caja"
import { ErrorApi } from "@/api/cliente"
import type { Documento } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import { Button } from "@/components/ui/button"
import { mensajeDeError, useEscribir } from "@/hooks/useComando"
import { pesos } from "@/lib/dinero"

const ESTADO: Record<Documento["estado"], string> = {
  pendiente: "Pendiente", enviando: "Emitiendo", emitido: "Emitido", rechazado: "Rechazado", fallido: "Fallido (se reintenta)",
}

export default function DocumentosCaja({ localId }: { localId: string }) {
  const escribir = useEscribir()
  const notificar = useNotificar()
  const [lista, setLista] = useState<Documento[] | null>(null)
  const [sinTurno, setSinTurno] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setLista((await pedirDocumentos(localId)).documentos)
      setSinTurno(false)
      setError(null)
    } catch (e) {
      if (e instanceof ErrorApi && e.codigo === "TURNO_NO_ABIERTO") setSinTurno(true)
      else setError(mensajeDeError(e))
    }
  }, [localId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  if (sinTurno) return <Aviso>Sin turno abierto</Aviso>
  return (
    <div className="space-y-3">
      {error && <Aviso tipo="error">{error}</Aviso>}
      {lista === null && !error && <p className="text-sm text-neutral-500">Cargando…</p>}
      {lista?.length === 0 && <p className="text-sm text-neutral-500">Todavía no hay documentos en este turno.</p>}
      {lista && lista.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr><th className="px-3 py-2">Documento</th><th className="px-3 py-2">Estado</th><th className="px-3 py-2">Folio</th><th className="px-3 py-2 text-right">Total</th><th /></tr>
            </thead>
            <tbody className="divide-y">
              {lista.map((d) => (
                <tr key={d.venta_id}>
                  <td className="px-3 py-2 capitalize">{d.tipo}</td>
                  <td className="px-3 py-2">{ESTADO[d.estado]}{d.motivo_rechazo && <span className="block text-xs text-red-700">{d.motivo_rechazo}</span>}</td>
                  <td className="px-3 py-2">{d.folio ?? "—"}</td>
                  <td className="px-3 py-2 text-right">{pesos(d.total)}</td>
                  <td className="px-3 py-2 text-right">
                    {d.estado === "emitido" && (
                      <Button type="button" size="sm" variant="outline"
                        onClick={() => void escribir(reimprimir(localId, d.venta_id), () => notificar("Enviado a la impresora", "ok"))}>
                        Reimprimir
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
