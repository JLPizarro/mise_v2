import { Minus, Pencil, Plus } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { Item, Pedido } from "@/api/tipos"
import { pesos } from "@/lib/dinero"

const MAX_CANTIDAD = 999

interface Props {
  numeroMesa: number | null
  pedido: Pedido | null
  /** Ítems agregados que todavía no confirma el servidor. */
  pendientes: Set<string>
  ocupado: boolean
  onCantidad: (item: Item, cantidad: number) => void
  onObservacion: (item: Item, observacion: string) => void
  onQuitar: (item: Item) => void
  onEnviar: () => void
  onPrecuenta: () => void
  onReabrir: () => void
}

export default function ComandaMesa({
  numeroMesa, pedido, pendientes, ocupado, onCantidad, onObservacion, onQuitar, onEnviar, onPrecuenta, onReabrir,
}: Props) {
  const [editando, setEditando] = useState<Item | null>(null)
  const [texto, setTexto] = useState("")
  const items = pedido?.items ?? []
  const enEspera = items.filter((i) => i.estado === "en_espera").length
  const enPrecuenta = pedido?.estado === "precuenta"

  return (
    <aside className="rounded-2xl border bg-white p-5 shadow-sm">
      <div className="mb-4">
        <h2 className="text-xl font-semibold">Comanda</h2>
        <p className="text-sm text-neutral-500">Mesa {numeroMesa !== null ? String(numeroMesa).padStart(2, "0") : ""}</p>
      </div>

      {enPrecuenta && (
        <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
          <p>La mesa está en precuenta.</p>
          <Button type="button" size="sm" className="mt-2" onClick={onReabrir} disabled={ocupado}>Reabrir mesa</Button>
        </div>
      )}

      {items.length === 0 ? (
        <div className="py-10 text-center text-sm text-neutral-500">Aún no hay productos en la comanda.</div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const modificable = item.estado === "en_espera" && !enPrecuenta
            return (
              <div key={item.item_id} className="rounded-xl border p-3">
                <div className="flex justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium">{item.cantidad} × {item.nombre}</p>
                    {item.modificador_nombre && (
                      <span className="mt-1 inline-block rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600">
                        {item.modificador_nombre}
                      </span>
                    )}
                    {item.observacion && (
                      <p className="mt-1 text-sm text-neutral-600"><span className="font-medium">Otro:</span> {item.observacion}</p>
                    )}
                    <p className="mt-1 text-sm text-neutral-500">{pesos(item.subtotal)}</p>
                  </div>
                  {modificable && (
                    <button type="button" disabled={ocupado} onClick={() => onQuitar(item)} className="self-start text-sm text-red-600 disabled:opacity-50">
                      Quitar
                    </button>
                  )}
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2 py-1 text-xs font-medium ${item.estado === "en_espera" ? "bg-amber-100 text-amber-800" : "bg-neutral-100 text-neutral-600"}`}>
                    {item.estado === "en_espera" ? "En espera" : "Enviado"}
                  </span>
                  {pendientes.has(item.item_id) && (
                    <span className="rounded-full bg-neutral-900 px-2 py-1 text-xs font-medium text-white">pendiente</span>
                  )}
                  {modificable && (
                    <div className="ml-auto flex items-center gap-1">
                      <Button type="button" variant="outline" size="icon" aria-label="Menos" disabled={ocupado || item.cantidad <= 1}
                        onClick={() => onCantidad(item, item.cantidad - 1)}><Minus /></Button>
                      <Button type="button" variant="outline" size="icon" aria-label="Más" disabled={ocupado || item.cantidad >= MAX_CANTIDAD}
                        onClick={() => onCantidad(item, item.cantidad + 1)}><Plus /></Button>
                      <Button type="button" variant="outline" size="icon" aria-label="Editar observación" disabled={ocupado}
                        onClick={() => { setEditando(item); setTexto(item.observacion ?? "") }}><Pencil /></Button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-6 border-t pt-5">
        <div className="flex items-center justify-between">
          <span className="font-medium">Total</span>
          <span className="text-2xl font-semibold">{pesos(pedido?.total ?? 0)}</span>
        </div>
        <Button type="button" className="mt-5 h-12 w-full" disabled={ocupado || enEspera === 0 || enPrecuenta} onClick={onEnviar}>
          Enviar a cocina ({enEspera})
        </Button>
        <Button type="button" variant="outline" className="mt-3 h-12 w-full" disabled={ocupado || items.length === 0 || enPrecuenta} onClick={onPrecuenta}>
          Precuenta
        </Button>
      </div>

      <Dialog open={editando !== null} onOpenChange={(v) => !v && setEditando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Observación</DialogTitle>
            <DialogDescription>{editando?.nombre}</DialogDescription>
          </DialogHeader>
          <textarea value={texto} maxLength={500} onChange={(e) => setTexto(e.target.value)} aria-label="Observación"
            className="min-h-24 w-full rounded-md border p-3 text-sm" placeholder="Ej: sin cilantro" />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setEditando(null)}>Cancelar</Button>
            <Button type="button" onClick={() => { if (editando) onObservacion(editando, texto.trim()); setEditando(null) }}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  )
}
