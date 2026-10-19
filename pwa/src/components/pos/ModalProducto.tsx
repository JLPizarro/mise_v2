import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { Modificador, Producto } from "@/api/tipos"
import { pesos } from "@/lib/dinero"

interface Props {
  producto: Producto | null
  onCerrar: () => void
  onConfirmar: (datos: { modificador: Modificador | null; observacion: string }) => void
}

/** Se monta de nuevo por producto (key), así parte siempre sin modificador ni observación. */
function Contenido({ producto, onCerrar, onConfirmar }: Props & { producto: Producto }) {
  const [modificador, setModificador] = useState<Modificador | null>(null)
  const [observacion, setObservacion] = useState("")

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{producto.nombre}</DialogTitle>
        <DialogDescription>Selecciona un modificador y agrega una observación si es necesario.</DialogDescription>
      </DialogHeader>

      {producto.modificadores.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm font-medium">Modificador</p>
          <div className="flex flex-wrap gap-2">
            {producto.modificadores.map((m) => (
              <Button
                key={m.modificador_id}
                type="button"
                variant={modificador?.modificador_id === m.modificador_id ? "default" : "outline"}
                onClick={() => setModificador(modificador?.modificador_id === m.modificador_id ? null : m)}
              >
                {m.nombre}
                {m.precio_adicional > 0 && ` (+${pesos(m.precio_adicional)})`}
              </Button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="observacion-producto">Otro</label>
        <textarea
          id="observacion-producto"
          value={observacion}
          maxLength={500}
          onChange={(e) => setObservacion(e.target.value)}
          placeholder="Ej: salsa aparte, sin cilantro..."
          className="min-h-24 w-full rounded-md border p-3 text-sm"
        />
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCerrar}>Cancelar</Button>
        <Button type="button" onClick={() => onConfirmar({ modificador, observacion: observacion.trim() })}>
          Agregar a comanda
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}

export default function ModalProducto({ producto, onCerrar, onConfirmar }: Props) {
  return (
    <Dialog open={producto !== null} onOpenChange={(v) => !v && onCerrar()}>
      {producto && <Contenido key={producto.producto_id} producto={producto} onCerrar={onCerrar} onConfirmar={onConfirmar} />}
    </Dialog>
  )
}
