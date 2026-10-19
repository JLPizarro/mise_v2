import type { Autorizador } from "@/api/tipos"
import { NOMBRE_ROL } from "@/sesion/roles"

interface Props {
  autorizadores: Autorizador[]
  autorizadorId: string
  codigo: string
  onAutorizador: (sub: string) => void
  onCodigo: (codigo: string) => void
}

/** Quién autoriza y su código personal. El código es de un solo uso en pantalla: el padre lo vacía al enviar. */
export default function AutorizacionAdmin({ autorizadores, autorizadorId, codigo, onAutorizador, onCodigo }: Props) {
  if (autorizadores.length === 0) {
    return <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      Ningún dueño o admin tiene código de autorización definido.
    </p>
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block space-y-1 text-sm">
        <span className="font-medium">Autoriza</span>
        <select value={autorizadorId} onChange={(e) => onAutorizador(e.target.value)} className="h-11 w-full rounded-lg border bg-white px-3">
          <option value="">Elige quién autoriza</option>
          {autorizadores.map((a) => <option key={a.sub} value={a.sub}>{a.nombre} ({NOMBRE_ROL[a.rol]})</option>)}
        </select>
      </label>
      <label className="block space-y-1 text-sm">
        <span className="font-medium">Código de autorización</span>
        <input type="password" inputMode="numeric" autoComplete="off" maxLength={8} value={codigo}
          onChange={(e) => onCodigo(e.target.value.replace(/\D/g, ""))} className="h-11 w-full rounded-lg border px-3" />
      </label>
    </div>
  )
}
