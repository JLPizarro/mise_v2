import { normalizarRut, rutValido } from "@/lib/rut"

interface Props {
  rut: string
  razonSocial: string
  onRut: (v: string) => void
  onRazonSocial: (v: string) => void
}

/** RUT sin puntos ni espacios, en mayúsculas (ej. 12345678-K), y razón social de 2 a 200 caracteres. */
export default function DatosFactura({ rut, razonSocial, onRut, onRazonSocial }: Props) {
  const rutMalo = rut !== "" && !rutValido(rut)
  return (
    <div className="space-y-3">
      <label className="block space-y-1 text-sm">
        <span className="font-medium">RUT</span>
        <input value={rut} maxLength={20} autoComplete="off" placeholder="12345678-5" aria-invalid={rutMalo}
          onChange={(e) => onRut(normalizarRut(e.target.value))} className="h-11 w-full rounded-lg border px-3" />
        {rutMalo && <span className="text-xs text-red-700">RUT inválido. Usa el formato 12345678-5</span>}
      </label>
      <label className="block space-y-1 text-sm">
        <span className="font-medium">Razón social</span>
        <input value={razonSocial} maxLength={200} autoComplete="off" onChange={(e) => onRazonSocial(e.target.value)}
          className="h-11 w-full rounded-lg border px-3" />
      </label>
    </div>
  )
}
