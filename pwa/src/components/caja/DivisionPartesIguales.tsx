import { useState } from "react"
import { Button } from "@/components/ui/button"
import { pesos } from "@/lib/dinero"

interface Props {
  personas: number
  partes: number[] | null
  pagadas: number
  onPersonas: (n: number) => void
  onDividir: () => void
}

/** Divide el saldo entre 2 y 20 personas; la próxima parte sin pagar es la que se cobra. */
export default function DivisionPartesIguales({ personas, partes, pagadas, onPersonas, onDividir }: Props) {
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-2">
        <label className="space-y-1 text-sm">
          <span className="font-medium">Personas</span>
          <input
            type="number"
            min={2}
            max={20}
            value={personas}
            disabled={pagadas > 0}
            onChange={(e) => onPersonas(Math.trunc(Number(e.target.value)) || 2)}
            className="block h-11 w-24 rounded-lg border px-3"
          />
        </label>
        <Button
          type="button"
          variant="outline"
          className="h-11"
          disabled={pagadas > 0}
          onClick={() => {
            try {
              onDividir()
              setError(null)
            } catch (e) {
              setError(e instanceof Error ? e.message : "No se pudo dividir")
            }
          }}
        >
          Dividir
        </Button>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {partes && (
        <ol className="space-y-1 text-sm">
          {partes.map((p, i) => (
            <li key={i} className={`flex justify-between rounded-lg border px-3 py-2 ${i < pagadas ? "bg-emerald-50 text-emerald-800" : i === pagadas ? "border-neutral-900" : ""}`}>
              <span>Parte {i + 1}{i < pagadas ? " · pagada" : i === pagadas ? " · a cobrar" : ""}</span>
              <span>{pesos(p)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
