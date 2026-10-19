import { useState } from "react"
import { finalizar, registrarPago, type Medio, type RespuestaPago } from "@/api/caja"
import { ErrorApi } from "@/api/cliente"
import { pedido as pedirPedido } from "@/api/pedidos"
import type { Pedido, TipoDocumento } from "@/api/tipos"
import DetalleCuenta from "@/components/caja/DetalleCuenta"
import DivisionCuenta from "@/components/caja/DivisionCuenta"
import DocumentoTributario from "@/components/caja/DocumentoTributario"
import FormularioPago from "@/components/caja/FormularioPago"
import ResumenPago from "@/components/caja/ResumenPago"
import SeleccionDocumento from "@/components/caja/SeleccionDocumento"
import { useDivision } from "@/components/caja/useDivision"
import { useNotificar } from "@/components/comun/avisos"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useEscribir } from "@/hooks/useComando"
import { propinaSugerida } from "@/lib/dinero"

interface Props {
  localId: string
  pedidoInicial: Pedido
  numeroMesa: number | null
  propinaPct: number
  onCerrar: () => void
  /** Algo cambió en el servidor (hay un pago o se cerró la venta): refrescar la lista. */
  onActualizado: () => void
  irATurno: () => void
}

/** Cobro de una mesa en precuenta: división, medios de pago, documento tributario. */
export default function CobroMesa({ localId, pedidoInicial, numeroMesa, propinaPct, onCerrar, onActualizado, irATurno }: Props) {
  const escribir = useEscribir()
  const notificar = useNotificar()
  const [pedido, setPedido] = useState<Pedido>(pedidoInicial)
  const division = useDivision(pedido)
  const [ultimoPago, setUltimoPago] = useState<RespuestaPago | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [emitido, setEmitido] = useState(false)

  const cobrado = pedido.saldo === 0
  const alError = (e: unknown): boolean => {
    if (e instanceof ErrorApi && e.codigo === "TURNO_NO_ABIERTO") {
      notificar("No hay turno abierto. Abre el turno para cobrar.", "info")
      onCerrar()
      irATurno()
      return true
    }
    return false
  }

  async function pagar(medios: Medio[]) {
    setOcupado(true)
    try {
      const respuesta = await escribir<RespuestaPago>(
        registrarPago(localId, pedido.pedido_id, {
          medios, tipo_division: division.tipo,
          items_cobrados: division.tipo === "items" ? division.itemsCobrados : undefined,
        }),
        undefined, alError,
      )
      if (!respuesta) return
      setUltimoPago(respuesta)
      division.alPagar()
      onActualizado()
      setPedido(await pedirPedido(localId, pedido.pedido_id))
    } finally {
      setOcupado(false)
    }
  }

  async function emitir(datos?: { tipo_documento: TipoDocumento; receptor?: { rut: string; razon_social: string } }) {
    setOcupado(true)
    try {
      const respuesta = await escribir<unknown>(finalizar(localId, pedido.pedido_id, datos), undefined, alError)
      if (!respuesta) return
      onActualizado()
      if (pedido.total === 0) {
        notificar("Mesa liberada", "ok")
        onCerrar()
        return
      }
      setEmitido(true)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Cobrar mesa {numeroMesa !== null ? String(numeroMesa).padStart(2, "0") : ""}</DialogTitle>
        </DialogHeader>

        <DetalleCuenta pedido={pedido} />
        {ultimoPago && <ResumenPago pago={ultimoPago} />}

        {emitido ? (
          <>
            <DocumentoTributario localId={localId} ventaId={pedido.pedido_id} />
            <Button type="button" className="h-11" onClick={onCerrar}>Listo</Button>
          </>
        ) : cobrado ? (
          <SeleccionDocumento total={pedido.total} ocupado={ocupado} onEmitir={(d) => void emitir(d)} />
        ) : (
          <>
            <DivisionCuenta pedido={pedido} division={division} />
            {division.monto > 0 && !division.error && (
              <FormularioPago
                key={`${division.tipo}-${division.monto}-${pedido.pagado}`}
                monto={division.monto}
                propinaInicial={propinaSugerida(division.monto, propinaPct)}
                ocupado={ocupado}
                onPagar={(medios) => void pagar(medios)}
              />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
