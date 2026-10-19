import type { Pedido } from "@/api/tipos"
import { pesos } from "@/lib/dinero"

interface Props { numero: number | null; sector: string | null; pedido: Pedido; onCobrar: () => void }

export default function TarjetaMesaCobro({ numero, sector, pedido, onCobrar }: Props) {
  return (
    <button type="button" onClick={onCobrar}
      className="w-full rounded-2xl border border-blue-200 bg-blue-50 p-4 text-left transition hover:shadow-md active:scale-[0.98]">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold">Mesa {numero !== null ? String(numero).padStart(2, "0") : "—"}</h3>
          {sector && <p className="text-xs text-neutral-500">{sector}</p>}
        </div>
        <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-blue-800">Precuenta</span>
      </div>
      <dl className="mt-4 space-y-0.5 text-sm">
        <div className="flex justify-between"><dt>Total</dt><dd>{pesos(pedido.total)}</dd></div>
        {pedido.pagado > 0 && <div className="flex justify-between"><dt>Pagado</dt><dd>{pesos(pedido.pagado)}</dd></div>}
        <div className="flex justify-between font-semibold"><dt>Saldo</dt><dd>{pesos(pedido.saldo)}</dd></div>
      </dl>
    </button>
  )
}
