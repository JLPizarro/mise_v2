import { CampoPesos } from "@/components/comun/CampoPesos"
import { pesos } from "@/lib/dinero"

interface Props { saldo: number; valor: string; onCambio: (valor: string) => void; error: string | null }

export default function MontoLibre({ saldo, valor, onCambio, error }: Props) {
  return (
    <div className="space-y-1">
      <CampoPesos etiqueta="Monto a cobrar" valor={valor} onCambio={onCambio} ayuda={`De $1 hasta el saldo (${pesos(saldo)})`} />
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
