import type { Pedido, TipoDivision } from "@/api/tipos"
import DivisionPartesIguales from "@/components/caja/DivisionPartesIguales"
import DivisionPorItems from "@/components/caja/DivisionPorItems"
import MontoLibre from "@/components/caja/MontoLibre"
import type { Division } from "@/components/caja/useDivision"
import { pesos } from "@/lib/dinero"

const TIPOS: { tipo: TipoDivision; nombre: string }[] = [
  { tipo: "completa", nombre: "Cuenta completa" },
  { tipo: "items", nombre: "Por ítems" },
  { tipo: "partes_iguales", nombre: "Partes iguales" },
  { tipo: "monto_libre", nombre: "Monto libre" },
]

export default function DivisionCuenta({ pedido, division }: { pedido: Pedido; division: Division }) {
  const bloqueado = division.tipo === "partes_iguales" && division.pagadas > 0

  return (
    <div className="space-y-3">
      <div role="tablist" aria-label="Tipo de división" className="flex flex-wrap gap-2">
        {TIPOS.map(({ tipo, nombre }) => (
          <button
            key={tipo}
            type="button"
            role="tab"
            aria-selected={division.tipo === tipo}
            disabled={bloqueado && tipo !== "partes_iguales"}
            onClick={() => division.setTipo(tipo)}
            className={`rounded-full px-3 py-1.5 text-sm font-medium disabled:opacity-40 ${division.tipo === tipo ? "bg-neutral-950 text-white" : "border bg-white"}`}
          >
            {nombre}
          </button>
        ))}
      </div>

      {division.tipo === "items" && (
        <DivisionPorItems items={pedido.items} seleccion={division.seleccion} onCambio={division.setSeleccion} />
      )}
      {division.tipo === "partes_iguales" && (
        <DivisionPartesIguales personas={division.personas} partes={division.partes} pagadas={division.pagadas}
          onPersonas={division.setPersonas} onDividir={division.dividir} />
      )}
      {division.tipo === "monto_libre" && (
        <MontoLibre saldo={pedido.saldo} valor={division.libre} onCambio={division.setLibre} error={division.error} />
      )}
      {division.tipo === "items" && division.error && <p className="text-sm text-red-700">{division.error}</p>}

      <p className="text-sm">A cobrar ahora: <strong>{pesos(division.monto)}</strong></p>
    </div>
  )
}
