import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { Rol } from "@/api/tipos"
import { NOMBRE_ROL } from "@/sesion/roles"

export interface Persona { sub: string; nombre: string; rol: Rol }

interface Props {
  abierto: boolean
  numeroMesa: number | null
  actual: string | null
  personas: Persona[]
  cargando: boolean
  onElegir: (garzonId: string | null) => void
  onCerrar: () => void
}

/** Asignar garzón: solo dueño y admin (P20). Incluye la opción «Sin garzón». */
export default function AsignarGarzon({ abierto, numeroMesa, actual, personas, cargando, onElegir, onCerrar }: Props) {
  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Asignar garzón</DialogTitle>
          <DialogDescription>Mesa {numeroMesa !== null ? String(numeroMesa).padStart(2, "0") : ""}</DialogDescription>
        </DialogHeader>
        {cargando ? (
          <p className="text-sm text-neutral-500">Cargando personal…</p>
        ) : (
          <ul className="max-h-72 space-y-2 overflow-y-auto">
            <li>
              <Button type="button" variant={actual === null ? "default" : "outline"} className="h-11 w-full justify-start" onClick={() => onElegir(null)}>
                Sin garzón
              </Button>
            </li>
            {personas.map((p) => (
              <li key={p.sub}>
                <Button type="button" variant={actual === p.sub ? "default" : "outline"} className="h-11 w-full justify-between" onClick={() => onElegir(p.sub)}>
                  <span>{p.nombre}</span>
                  <span className="text-xs opacity-70">{NOMBRE_ROL[p.rol]}</span>
                </Button>
              </li>
            ))}
          </ul>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCerrar}>Cancelar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
