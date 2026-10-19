import type { RespuestaPago } from "@/api/caja"
import { pesos } from "@/lib/dinero"

const NOMBRE: Record<string, string> = { efectivo: "Efectivo", debito: "Débito", credito: "Crédito", transferencia: "Transferencia" }

export default function ResumenPago({ pago }: { pago: RespuestaPago }) {
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
      <p className="font-medium">Pago registrado</p>
      <ul className="mt-1 space-y-0.5">
        {pago.pagos.map((p) => (
          <li key={p.pago_id}>
            {NOMBRE[p.metodo] ?? p.metodo}: {pesos(p.monto)}
            {p.propina > 0 && ` + propina ${pesos(p.propina)}`}
            {p.vuelto !== null && p.vuelto > 0 && ` · vuelto ${pesos(p.vuelto)}`}
          </li>
        ))}
      </ul>
      <p className="mt-1">Saldo: {pesos(pago.pedido.saldo)}</p>
    </div>
  )
}
