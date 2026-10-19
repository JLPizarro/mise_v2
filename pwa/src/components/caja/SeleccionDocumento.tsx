import { useState } from "react"
import type { TipoDocumento } from "@/api/tipos"
import DatosFactura from "@/components/caja/DatosFactura"
import { Button } from "@/components/ui/button"
import { facturaValida, normalizarRut } from "@/lib/rut"

interface Props {
  total: number
  ocupado: boolean
  onEmitir: (datos?: { tipo_documento: TipoDocumento; receptor?: { rut: string; razon_social: string } }) => void
}

/** Con el saldo en cero: boleta o factura. Si el total es 0, solo se libera la mesa. */
export default function SeleccionDocumento({ total, ocupado, onEmitir }: Props) {
  const [tipo, setTipo] = useState<TipoDocumento>("boleta")
  const [rut, setRut] = useState("")
  const [razonSocial, setRazonSocial] = useState("")

  if (total === 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-neutral-600">La mesa no tiene consumo.</p>
        <Button type="button" className="h-12 w-full" disabled={ocupado} onClick={() => onEmitir()}>Liberar mesa sin consumo</Button>
      </div>
    )
  }

  const valida = tipo === "boleta" || facturaValida(rut, razonSocial)
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">Documento tributario</p>
      <div className="flex gap-2" role="radiogroup" aria-label="Documento tributario">
        {(["boleta", "factura"] as const).map((t) => (
          <button key={t} type="button" role="radio" aria-checked={tipo === t} onClick={() => setTipo(t)}
            className={`flex-1 rounded-xl border px-4 py-3 text-sm font-medium capitalize ${tipo === t ? "border-neutral-950 bg-neutral-950 text-white" : "bg-white"}`}>
            {t}
          </button>
        ))}
      </div>
      {tipo === "factura" && <DatosFactura rut={rut} razonSocial={razonSocial} onRut={setRut} onRazonSocial={setRazonSocial} />}
      <Button type="button" className="h-12 w-full" disabled={ocupado || !valida}
        onClick={() => onEmitir(tipo === "boleta"
          ? { tipo_documento: "boleta" }
          : { tipo_documento: "factura", receptor: { rut: normalizarRut(rut), razon_social: razonSocial.trim() } })}>
        Emitir {tipo}
      </Button>
    </div>
  )
}
