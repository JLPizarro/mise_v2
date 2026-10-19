import { Minus, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { Item } from "@/api/tipos"
import { pesos } from "@/lib/dinero"

interface Props {
  items: Item[]
  seleccion: Record<string, number>
  onCambio: (seleccion: Record<string, number>) => void
}

/** Cuánto cobrar de cada ítem: hasta `cantidad - cobrado`. */
export default function DivisionPorItems({ items, seleccion, onCambio }: Props) {
  const mover = (item: Item, delta: number) => {
    const disponible = item.cantidad - item.cobrado
    const actual = seleccion[item.item_id] ?? 0
    onCambio({ ...seleccion, [item.item_id]: Math.max(0, Math.min(disponible, actual + delta)) })
  }

  return (
    <ul className="space-y-2">
      {items.map((item) => {
        const disponible = item.cantidad - item.cobrado
        const actual = seleccion[item.item_id] ?? 0
        return (
          <li key={item.item_id} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
            <div className="min-w-0">
              <p className="font-medium">{item.nombre}</p>
              <p className="text-xs text-neutral-500">
                {disponible > 0 ? `${disponible} por cobrar · ${pesos(item.precio_unitario)} c/u` : "Ya cobrado"}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <Button type="button" variant="outline" size="icon" aria-label={`Menos ${item.nombre}`} disabled={actual === 0} onClick={() => mover(item, -1)}><Minus /></Button>
              <span className="w-6 text-center" aria-label={`Cantidad de ${item.nombre}`}>{actual}</span>
              <Button type="button" variant="outline" size="icon" aria-label={`Más ${item.nombre}`} disabled={actual >= disponible} onClick={() => mover(item, 1)}><Plus /></Button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
