import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { listar } from "@/api/admin"
import { escribir } from "@/api/escribir"
import { asignarGarzon, bloquearMesa } from "@/api/salon"
import type { EstadoMesaSolo, MesaPlano, Rol } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import AsignarGarzon, { type Persona } from "@/components/pos/AsignarGarzon"
import TableCard from "@/components/pos/TableCard"
import { mensajeDeError } from "@/hooks/useComando"
import { etiquetaPendiente, useComandosPendientes } from "@/hooks/usePendientes"
import { usePlano } from "@/hooks/usePlano"
import { estadoMesa } from "@/offline/pedidoLocal"
import { puede, ROLES } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

const ROLES_ASIGNABLES: Rol[] = ["dueno", "admin", "cajero", "garzon"]

interface FilaPersonal { sub: string | null; nombre: string; rol: Rol; estado: string; invitacion: boolean }

export default function TablesPage() {
  const { local, rol, sesion } = useSesion()
  const localId = local!.local_id
  const navigate = useNavigate()
  const notificar = useNotificar()
  const { plano, error, desdeCache, mezclar } = usePlano(localId)
  const pendientes = useComandosPendientes(localId)
  const [sectorElegido, setSectorElegido] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [asignando, setAsignando] = useState<MesaPlano | null>(null)
  const [personas, setPersonas] = useState<Persona[] | null>(null)

  const puedeBloquear = puede(rol, ROLES.bloquear)
  const puedeAsignar = puede(rol, ROLES.asignarGarzon)

  const sectores = useMemo(() => plano?.sectores.filter((s) => s.activo) ?? [], [plano])
  const sectorActual = sectorElegido ?? sectores[0]?.sector_id ?? null
  const mesas = useMemo(
    () =>
      (plano?.mesas ?? [])
        .filter((m) => m.sector_id === sectorActual)
        .sort((a, b) => a.numero - b.numero)
        .map((m) => estadoMesa(m, pendientes.filter((c) => c.mesaId === m.mesa_id))),
    [plano, sectorActual, pendientes],
  )
  const nombres = useMemo(() => new Map((personas ?? []).map((p) => [p.sub, p.nombre])), [personas])

  async function cambiarBloqueo(mesa: MesaPlano) {
    setOcupado(true)
    try {
      const estado = await escribir<EstadoMesaSolo>(bloquearMesa(localId, mesa.mesa_id, mesa.estado !== "bloqueada"))
      mezclar([estado])
    } catch (e) {
      notificar(mensajeDeError(e), "error")
    } finally {
      setOcupado(false)
    }
  }

  async function abrirAsignacion(mesa: MesaPlano) {
    setAsignando(mesa)
    if (personas !== null) return
    try {
      const { personal } = await listar<{ personal: FilaPersonal[] }>(localId, "personal")
      setPersonas(
        personal
          .filter((p) => p.estado === "activo" && !p.invitacion && p.sub && ROLES_ASIGNABLES.includes(p.rol))
          .map((p) => ({ sub: p.sub as string, nombre: p.nombre, rol: p.rol })),
      )
    } catch (e) {
      notificar(mensajeDeError(e), "error")
      setAsignando(null)
    }
  }

  async function asignar(garzonId: string | null) {
    if (!asignando) return
    setOcupado(true)
    try {
      mezclar([await escribir<EstadoMesaSolo>(asignarGarzon(localId, asignando.mesa_id, garzonId))])
      setAsignando(null)
    } catch (e) {
      notificar(mensajeDeError(e), "error")
    } finally {
      setOcupado(false)
    }
  }

  function seleccionar(mesa: MesaPlano) {
    if (mesa.estado === "bloqueada") {
      notificar("La mesa está bloqueada", "info")
      return
    }
    navigate(`/l/${localId}/salon/mesas/${mesa.mesa_id}`)
  }

  return (
    <section>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-950">Salón</h1>
        <p className="mt-1 text-sm text-neutral-500">Selecciona una mesa para comenzar o continuar una atención.</p>
      </div>

      {error && <Aviso tipo="error" className="mb-4">{error}</Aviso>}
      {desdeCache && <Aviso className="mb-4">Mostrando el último plano guardado en este equipo.</Aviso>}

      <div className="mb-5 flex gap-2 overflow-x-auto pb-1">
        {sectores.map((s) => (
          <button
            key={s.sector_id}
            type="button"
            onClick={() => setSectorElegido(s.sector_id)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition ${
              sectorActual === s.sector_id ? "bg-neutral-950 text-white" : "border border-neutral-200 bg-white text-neutral-700"
            }`}
          >
            {s.nombre}
          </button>
        ))}
      </div>

      {!plano && !error && <p className="text-sm text-neutral-500">Cargando mesas…</p>}
      {plano && plano.mesas.length === 0 && <p className="text-sm text-neutral-500">Todavía no hay mesas configuradas.</p>}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {mesas.map((m) => (
          <TableCard
            key={m.mesa_id}
            mesa={m}
            sub={sesion.sub}
            etiqueta={etiquetaPendiente(localId, m.mesa_id, pendientes)}
            puedeBloquear={puedeBloquear}
            puedeAsignar={puedeAsignar}
            nombreGarzon={m.garzon_id ? nombres.get(m.garzon_id) : undefined}
            ocupado={ocupado}
            onSeleccionar={seleccionar}
            onBloquear={(mesa) => void cambiarBloqueo(mesa)}
            onAsignar={(mesa) => void abrirAsignacion(mesa)}
          />
        ))}
      </div>

      <AsignarGarzon
        abierto={asignando !== null}
        numeroMesa={asignando?.numero ?? null}
        actual={asignando?.garzon_id ?? null}
        personas={personas ?? []}
        cargando={personas === null}
        onElegir={(id) => void asignar(id)}
        onCerrar={() => setAsignando(null)}
      />
    </section>
  )
}
