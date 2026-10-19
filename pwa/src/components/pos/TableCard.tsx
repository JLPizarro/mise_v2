import type { EstadoMesa, MesaPlano } from "@/api/tipos"
import { cn } from "@/lib/utils"

interface Props {
  mesa: MesaPlano
  /** `sub` de la persona que ingresó: marca «Tu mesa». */
  sub: string
  etiqueta: "Sincronizando" | "Guardada en este equipo" | null
  puedeBloquear: boolean
  puedeAsignar: boolean
  nombreGarzon?: string
  ocupado: boolean
  onSeleccionar: (mesa: MesaPlano) => void
  onBloquear: (mesa: MesaPlano) => void
  onAsignar: (mesa: MesaPlano) => void
}

const ETIQUETA_ESTADO: Record<EstadoMesa, string> = {
  libre: "Libre", ocupada: "Ocupada", precuenta: "Precuenta", bloqueada: "Bloqueada",
}
const ESTILO_ESTADO: Record<EstadoMesa, string> = {
  libre: "border-emerald-200 bg-emerald-50",
  ocupada: "border-amber-200 bg-amber-50",
  precuenta: "border-blue-200 bg-blue-50",
  bloqueada: "border-neutral-200 bg-neutral-100",
}
const PUNTO_ESTADO: Record<EstadoMesa, string> = {
  libre: "bg-emerald-500", ocupada: "bg-amber-500", precuenta: "bg-blue-500", bloqueada: "bg-neutral-400",
}

export default function TableCard({
  mesa, sub, etiqueta, puedeBloquear, puedeAsignar, nombreGarzon, ocupado, onSeleccionar, onBloquear, onAsignar,
}: Props) {
  const bloqueada = mesa.estado === "bloqueada"
  const esMia = mesa.garzon_id !== null && mesa.garzon_id === sub

  return (
    <div className={cn("flex min-h-36 flex-col rounded-2xl border", ESTILO_ESTADO[mesa.estado], bloqueada && "opacity-70")}>
      <button
        type="button"
        onClick={() => onSeleccionar(mesa)}
        className="flex-1 rounded-2xl p-4 text-left transition active:scale-[0.98]"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-neutral-950">Mesa {String(mesa.numero).padStart(2, "0")}</h3>
            <p className="mt-1 text-sm text-neutral-600">{ETIQUETA_ESTADO[mesa.estado]}</p>
          </div>
          <span className={cn("h-3 w-3 rounded-full", PUNTO_ESTADO[mesa.estado])} />
        </div>
        <div className="mt-4 space-y-1">
          <p className="text-xs text-neutral-500">Capacidad: {mesa.capacidad} personas</p>
          {esMia && <p className="text-xs font-medium text-neutral-700">Tu mesa</p>}
          {!esMia && nombreGarzon && <p className="text-xs text-neutral-500">Garzón: {nombreGarzon}</p>}
          {etiqueta && (
            <p className="inline-block rounded-full bg-white/80 px-2 py-0.5 text-xs font-medium text-neutral-700">{etiqueta}</p>
          )}
        </div>
      </button>
      {(puedeBloquear || puedeAsignar) && (
        <div className="flex gap-2 border-t border-black/5 px-3 py-2 text-xs">
          {puedeBloquear && (
            <button type="button" disabled={ocupado} className="font-medium text-neutral-700 underline disabled:opacity-50" onClick={() => onBloquear(mesa)}>
              {bloqueada ? "Desbloquear" : "Bloquear"}
            </button>
          )}
          {puedeAsignar && (
            <button type="button" disabled={ocupado} className="font-medium text-neutral-700 underline disabled:opacity-50" onClick={() => onAsignar(mesa)}>
              Asignar garzón
            </button>
          )}
        </div>
      )}
    </div>
  )
}
