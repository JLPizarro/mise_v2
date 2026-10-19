import type { ReactNode } from "react"
import { Aviso } from "@/components/comun/Aviso"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"

export function Tarjeta({ titulo, acciones, children }: { titulo: string; acciones?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-3 rounded-2xl border bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">{titulo}</h2>
        {acciones}
      </div>
      {children}
    </section>
  )
}

export function Campo({ etiqueta, ayuda, children }: { etiqueta: string; ayuda?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium">{etiqueta}</span>
      {children}
      {ayuda && <span className="block text-xs text-neutral-500">{ayuda}</span>}
    </label>
  )
}

interface FormDialogProps {
  abierto: boolean
  titulo: string
  descripcion?: string
  guardando: boolean
  puedeGuardar?: boolean
  error?: string | null
  etiquetaGuardar?: string
  onGuardar: () => void
  onCerrar: () => void
  children: ReactNode
}

/** Formulario en un diálogo: Cancelar / Guardar, con el error del servidor tal cual. */
export function FormDialog({ abierto, titulo, descripcion, guardando, puedeGuardar = true, error, etiquetaGuardar = "Guardar", onGuardar, onCerrar, children }: FormDialogProps) {
  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          {descripcion && <DialogDescription>{descripcion}</DialogDescription>}
        </DialogHeader>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (puedeGuardar && !guardando) onGuardar() }}>
          {children}
          {error && <Aviso tipo="error">{error}</Aviso>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCerrar}>Cancelar</Button>
            <Button type="submit" disabled={guardando || !puedeGuardar}>{etiquetaGuardar}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Insignia({ activo, textoActivo = "Activo", textoInactivo = "Inactivo" }: { activo: boolean; textoActivo?: string; textoInactivo?: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${activo ? "bg-emerald-100 text-emerald-800" : "bg-neutral-200 text-neutral-600"}`}>
      {activo ? textoActivo : textoInactivo}
    </span>
  )
}
