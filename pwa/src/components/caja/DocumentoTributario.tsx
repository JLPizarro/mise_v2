import { useEffect, useState } from "react"
import { documento as pedirDocumento, reimprimir } from "@/api/caja"
import type { Documento } from "@/api/tipos"
import { Button } from "@/components/ui/button"
import { useEscribir } from "@/hooks/useComando"

const CADA_MS = 3000
const MAXIMO_MS = 60_000

/** Estado del documento tributario de una venta: consulta cada 3 s hasta 60 s (P18). */
export default function DocumentoTributario({ localId, ventaId }: { localId: string; ventaId: string }) {
  const [documento, setDocumento] = useState<Documento | null>(null)
  const [vencido, setVencido] = useState(false)
  const escribir = useEscribir()
  const [reimpreso, setReimpreso] = useState(false)

  useEffect(() => {
    let vigente = true
    const inicio = Date.now()
    let temporizador: number | undefined
    const consultar = async () => {
      try {
        const d = await pedirDocumento(localId, ventaId)
        if (!vigente) return
        setDocumento(d)
        if (d.estado === "emitido" || d.estado === "rechazado") return
      } catch {
        /* se reintenta */
      }
      if (!vigente) return
      if (Date.now() - inicio >= MAXIMO_MS) {
        setVencido(true)
        return
      }
      temporizador = window.setTimeout(() => void consultar(), CADA_MS)
    }
    void consultar()
    return () => {
      vigente = false
      window.clearTimeout(temporizador)
    }
  }, [localId, ventaId])

  const estado = documento?.estado
  return (
    <div className="space-y-3 rounded-xl border p-4 text-sm" aria-live="polite">
      {(estado === undefined || estado === "pendiente" || estado === "enviando") && !vencido && <p>Emitiendo…</p>}
      {vencido && estado !== "emitido" && estado !== "rechazado" && (
        <p>Sigue en proceso. Revisa la pestaña Documentos en unos minutos.</p>
      )}
      {estado === "emitido" && (
        <>
          <p className="font-medium text-emerald-700">Folio {documento?.folio}</p>
          <Button type="button" variant="outline" disabled={reimpreso}
            onClick={() => void escribir(reimprimir(localId, ventaId), () => setReimpreso(true))}>
            {reimpreso ? "Enviado a la impresora" : "Reimprimir"}
          </Button>
        </>
      )}
      {estado === "rechazado" && <p className="text-red-700">Rechazado: {documento?.motivo_rechazo}</p>}
      {estado === "fallido" && <p>No se pudo emitir; se reintenta automáticamente.</p>}
    </div>
  )
}
