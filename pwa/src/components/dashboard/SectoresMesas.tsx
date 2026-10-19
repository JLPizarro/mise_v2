import { useState } from "react"
import { crear, editar } from "@/api/admin"
import type { Sector } from "@/api/tipos"
import { Campo, FormDialog, Insignia, Tarjeta } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { useAdminLista } from "@/hooks/useAdmin"
import { useGuardar } from "@/hooks/useGuardar"
import { aEntero } from "@/lib/dinero"
import { CLASE_INPUT } from "@/lib/estilos"

interface MesaAdmin { mesa_id: string; sector_id: string; sector_nombre: string; numero: number; capacidad: number; activa: boolean }

function FormularioSector({ localId, sector, onCerrar, onGuardado }: { localId: string; sector: Sector | null; onCerrar: () => void; onGuardado: () => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState(sector?.nombre ?? "")
  const [activo, setActivo] = useState(sector?.activo ?? true)
  return (
    <FormDialog abierto titulo={sector ? "Editar sector" : "Nuevo sector"} guardando={guardando} puedeGuardar={nombre.trim() !== ""} error={error}
      onCerrar={onCerrar}
      onGuardar={() => void guardar(sector ? editar(localId, "sectores", sector.sector_id, { nombre: nombre.trim(), activo }) : crear(localId, "sectores", { nombre: nombre.trim(), activo }),
        () => { onGuardado(); onCerrar() })}>
      <Campo etiqueta="Nombre"><input className={CLASE_INPUT} value={nombre} maxLength={80} onChange={(e) => setNombre(e.target.value)} /></Campo>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo</label>
    </FormDialog>
  )
}

function FormularioMesa({ localId, mesa, sectores, onCerrar, onGuardado }: { localId: string; mesa: MesaAdmin | null; sectores: Sector[]; onCerrar: () => void; onGuardado: () => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [sectorId, setSectorId] = useState(mesa?.sector_id ?? sectores.find((s) => s.activo)?.sector_id ?? "")
  const [numero, setNumero] = useState(mesa ? String(mesa.numero) : "")
  const [capacidad, setCapacidad] = useState(mesa ? String(mesa.capacidad) : "4")
  const [activa, setActiva] = useState(mesa?.activa ?? true)
  const n = aEntero(numero)
  const cap = aEntero(capacidad)
  return (
    <FormDialog abierto titulo={mesa ? "Editar mesa" : "Nueva mesa"} guardando={guardando} puedeGuardar={sectorId !== "" && n !== null && n > 0 && (cap === null || cap > 0)}
      error={error} onCerrar={onCerrar}
      onGuardar={() => void guardar(
        mesa ? editar(localId, "mesas", mesa.mesa_id, { numero: n, capacidad: cap ?? undefined, sector_id: sectorId, activa })
          : crear(localId, "mesas", { sector_id: sectorId, numero: n, capacidad: cap ?? undefined }),
        () => { onGuardado(); onCerrar() })}>
      <Campo etiqueta="Sector">
        <select className={CLASE_INPUT} value={sectorId} onChange={(e) => setSectorId(e.target.value)}>
          {sectores.map((s) => <option key={s.sector_id} value={s.sector_id}>{s.nombre}</option>)}
        </select>
      </Campo>
      <div className="grid grid-cols-2 gap-3">
        <Campo etiqueta="Número"><input className={CLASE_INPUT} inputMode="numeric" value={numero} onChange={(e) => setNumero(e.target.value.replace(/\D/g, ""))} /></Campo>
        <Campo etiqueta="Capacidad"><input className={CLASE_INPUT} inputMode="numeric" value={capacidad} onChange={(e) => setCapacidad(e.target.value.replace(/\D/g, ""))} /></Campo>
      </div>
      {mesa && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activa} onChange={(e) => setActiva(e.target.checked)} /> Activa</label>}
    </FormDialog>
  )
}

/** Sectores y mesas. No hay borrado: se desactivan. */
export default function SectoresMesas({ localId }: { localId: string }) {
  const sectores = useAdminLista<Sector>(localId, "sectores")
  const mesas = useAdminLista<MesaAdmin>(localId, "mesas")
  const [sector, setSector] = useState<Sector | "nuevo" | null>(null)
  const [mesa, setMesa] = useState<MesaAdmin | "nueva" | null>(null)
  const recargar = () => { void sectores.recargar(); void mesas.recargar() }

  return (
    <div className="space-y-4">
      <Tarjeta titulo="Sectores" acciones={<Button type="button" size="sm" onClick={() => setSector("nuevo")}>Nuevo sector</Button>}>
        <ul className="divide-y text-sm">
          {sectores.datos?.map((s) => (
            <li key={s.sector_id} className="flex items-center justify-between gap-2 py-2">
              <span className="flex items-center gap-2">{s.nombre} <Insignia activo={s.activo} /></span>
              <Button type="button" size="sm" variant="outline" onClick={() => setSector(s)}>Editar</Button>
            </li>
          ))}
        </ul>
      </Tarjeta>
      <Tarjeta titulo="Mesas" acciones={<Button type="button" size="sm" disabled={!sectores.datos?.length} onClick={() => setMesa("nueva")}>Nueva mesa</Button>}>
        <ul className="divide-y text-sm">
          {mesas.datos?.slice().sort((a, b) => a.numero - b.numero).map((m) => (
            <li key={m.mesa_id} className="flex items-center justify-between gap-2 py-2">
              <span className="flex items-center gap-2">Mesa {m.numero} · {m.sector_nombre} · {m.capacidad} personas <Insignia activo={m.activa} textoActivo="Activa" textoInactivo="Inactiva" /></span>
              <Button type="button" size="sm" variant="outline" onClick={() => setMesa(m)}>Editar</Button>
            </li>
          ))}
        </ul>
      </Tarjeta>
      {sector && <FormularioSector localId={localId} sector={sector === "nuevo" ? null : sector} onCerrar={() => setSector(null)} onGuardado={recargar} />}
      {mesa && sectores.datos && <FormularioMesa localId={localId} mesa={mesa === "nueva" ? null : mesa} sectores={sectores.datos} onCerrar={() => setMesa(null)} onGuardado={recargar} />}
    </div>
  )
}
