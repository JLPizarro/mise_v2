import { cn } from "@/lib/utils"

interface Props {
  etiqueta: string
  valor: string
  onCambio: (valor: string) => void
  ayuda?: string
  deshabilitado?: boolean
  className?: string
}

/** Campo numérico de pesos enteros. El valor se guarda como texto (solo dígitos). */
export function CampoPesos({ etiqueta, valor, onCambio, ayuda, deshabilitado, className }: Props) {
  return (
    <label className={cn("block space-y-1 text-sm", className)}>
      <span className="font-medium">{etiqueta}</span>
      <input
        type="text"
        inputMode="numeric"
        autoComplete="off"
        disabled={deshabilitado}
        value={valor}
        onChange={(e) => onCambio(e.target.value.replace(/\D/g, ""))}
        className="h-11 w-full rounded-lg border bg-white px-3 text-base disabled:opacity-50"
      />
      {ayuda && <span className="block text-xs text-neutral-500">{ayuda}</span>}
    </label>
  )
}
