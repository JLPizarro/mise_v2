import { useCallback, useState, type ReactNode } from "react"
import { NotificacionesContexto, type TipoAviso } from "@/components/comun/avisos"
import { cn } from "@/lib/utils"

interface Toast { id: number; texto: string; tipo: TipoAviso }
const DURACION_MS = 5000
let contador = 0

const ESTILOS: Record<TipoAviso, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  info: "border-neutral-200 bg-white text-neutral-900",
  error: "border-red-200 bg-red-50 text-red-900",
}

export function Notificaciones({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Toast[]>([])

  const notificar = useCallback((texto: string, tipo: TipoAviso = "info") => {
    const id = ++contador
    setAvisos((actuales) => [...actuales.slice(-3), { id, texto, tipo }])
    window.setTimeout(() => setAvisos((actuales) => actuales.filter((a) => a.id !== id)), DURACION_MS)
  }, [])

  return (
    <NotificacionesContexto.Provider value={notificar}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {avisos.map((a) => (
          <div key={a.id} role="status" className={cn("pointer-events-auto w-full max-w-md rounded-xl border px-4 py-3 text-sm shadow-lg", ESTILOS[a.tipo])}>
            {a.texto}
          </div>
        ))}
      </div>
    </NotificacionesContexto.Provider>
  )
}
