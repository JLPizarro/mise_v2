import type { Pedido } from "@/api/tipos"
import { pesos } from "@/lib/dinero"

export default function DetalleCuenta({ pedido }: { pedido: Pedido }) {
  return (
    <div className="rounded-xl border">
      <ul className="divide-y text-sm">
        {pedido.items.map((i) => (
          <li key={i.item_id} className="flex items-start justify-between gap-3 px-3 py-2">
            <div className="min-w-0">
              <p className="font-medium">{i.cantidad} × {i.nombre}</p>
              {i.modificador_nombre && <p className="text-xs text-neutral-500">{i.modificador_nombre}</p>}
              {i.cobrado > 0 && <p className="text-xs text-emerald-700">Cobrado: {i.cobrado} de {i.cantidad}</p>}
            </div>
            <span className="shrink-0">{pesos(i.subtotal)}</span>
          </li>
        ))}
      </ul>
      <dl className="space-y-1 border-t bg-neutral-50 px-3 py-3 text-sm">
        <div className="flex justify-between"><dt>Total</dt><dd className="font-semibold">{pesos(pedido.total)}</dd></div>
        <div className="flex justify-between"><dt>Pagado</dt><dd>{pesos(pedido.pagado)}</dd></div>
        <div className="flex justify-between text-base"><dt className="font-medium">Saldo</dt><dd className="font-semibold">{pesos(pedido.saldo)}</dd></div>
      </dl>
    </div>
  )
}
