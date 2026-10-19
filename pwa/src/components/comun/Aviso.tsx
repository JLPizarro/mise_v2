import type { ReactNode } from "react"
import type { TipoAviso } from "@/components/comun/avisos"
import { cn } from "@/lib/utils"

const ESTILOS: Record<TipoAviso, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  info: "border-blue-200 bg-blue-50 text-blue-900",
  error: "border-red-200 bg-red-50 text-red-900",
}

/** Mensaje fijo dentro de una pantalla (a diferencia del toast, no desaparece solo). */
export function Aviso({ tipo = "info", children, className }: { tipo?: TipoAviso; children: ReactNode; className?: string }) {
  return (
    <div role={tipo === "error" ? "alert" : "status"} className={cn("rounded-xl border px-4 py-3 text-sm", ESTILOS[tipo], className)}>
      {children}
    </div>
  )
}
