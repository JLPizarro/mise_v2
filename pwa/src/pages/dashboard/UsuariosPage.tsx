import { useState } from "react"
import { crear, editar, eliminar, idDeEmail } from "@/api/admin"
import type { Rol } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { Campo, FormDialog, Insignia, Tarjeta } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { useAdminLista } from "@/hooks/useAdmin"
import { useEscribir } from "@/hooks/useComando"
import { useGuardar } from "@/hooks/useGuardar"
import { CLASE_INPUT } from "@/lib/estilos"
import { NOMBRE_ROL } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

interface Persona { sub: string | null; nombre: string; email: string; rol: Rol; estado: string; invitacion: boolean }
const TODOS_LOS_ROLES: Rol[] = ["dueno", "admin", "cajero", "garzon", "cocina"]

function FormularioInvitacion({ localId, roles, onCerrar, onGuardado }: { localId: string; roles: Rol[]; onCerrar: () => void; onGuardado: () => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [email, setEmail] = useState("")
  const [nombre, setNombre] = useState("")
  const [rol, setRol] = useState<Rol>(roles.includes("garzon") ? "garzon" : roles[0])
  return (
    <FormDialog abierto titulo="Invitar a una persona" descripcion="Podrá ingresar con esa cuenta de Google." guardando={guardando}
      puedeGuardar={/^\S+@\S+\.\S+$/.test(email.trim()) && nombre.trim() !== ""} error={error} etiquetaGuardar="Invitar" onCerrar={onCerrar}
      onGuardar={() => void guardar(crear(localId, "personal", { email: email.trim().toLowerCase(), nombre: nombre.trim(), rol }), () => { onGuardado(); onCerrar() })}>
      <Campo etiqueta="Email"><input type="email" className={CLASE_INPUT} value={email} maxLength={200} onChange={(e) => setEmail(e.target.value)} /></Campo>
      <Campo etiqueta="Nombre"><input className={CLASE_INPUT} value={nombre} maxLength={120} onChange={(e) => setNombre(e.target.value)} /></Campo>
      <Campo etiqueta="Rol">
        <select className={CLASE_INPUT} value={rol} onChange={(e) => setRol(e.target.value as Rol)}>
          {roles.map((r) => <option key={r} value={r}>{NOMBRE_ROL[r]}</option>)}
        </select>
      </Campo>
    </FormDialog>
  )
}

function FormularioPersona({ localId, persona, esUnoMismo, roles, onCerrar, onGuardado }: { localId: string; persona: Persona; esUnoMismo: boolean; roles: Rol[]; onCerrar: () => void; onGuardado: () => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState(persona.nombre)
  const [rol, setRol] = useState<Rol>(persona.rol)
  const [estado, setEstado] = useState(persona.estado)
  const opciones = roles.includes(persona.rol) ? roles : [persona.rol, ...roles]
  return (
    <FormDialog abierto titulo={`Editar a ${persona.nombre}`} guardando={guardando} puedeGuardar={nombre.trim() !== ""} error={error} onCerrar={onCerrar}
      onGuardar={() => void guardar(editar(localId, "personal", persona.sub as string, {
        nombre: nombre.trim(), rol: esUnoMismo ? undefined : rol, estado: esUnoMismo ? undefined : estado,
      }), () => { onGuardado(); onCerrar() })}>
      <Campo etiqueta="Nombre"><input className={CLASE_INPUT} value={nombre} maxLength={120} onChange={(e) => setNombre(e.target.value)} /></Campo>
      {esUnoMismo ? (
        <p className="text-sm text-neutral-500">No puedes cambiar tu propio rol ni tu estado.</p>
      ) : (
        <>
          <Campo etiqueta="Rol">
            <select className={CLASE_INPUT} value={rol} onChange={(e) => setRol(e.target.value as Rol)}>
              {opciones.map((r) => <option key={r} value={r}>{NOMBRE_ROL[r]}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Estado">
            <select className={CLASE_INPUT} value={estado} onChange={(e) => setEstado(e.target.value)}>
              <option value="activo">Activo</option><option value="archivado">Archivado</option>
            </select>
          </Campo>
        </>
      )}
    </FormDialog>
  )
}

export default function UsuariosPage() {
  const { local, rol, sesion } = useSesion()
  const localId = local!.local_id
  const escribir = useEscribir()
  const personal = useAdminLista<Persona>(localId, "personal")
  const [invitando, setInvitando] = useState(false)
  const [editando, setEditando] = useState<Persona | null>(null)
  // El admin no puede dar ni quitar el rol de dueño.
  const rolesPermitidos = TODOS_LOS_ROLES.filter((r) => rol === "dueno" || r !== "dueno")

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Personal</h1>
        <Button type="button" onClick={() => setInvitando(true)}>Invitar persona</Button>
      </div>
      {personal.error && <Aviso tipo="error">{personal.error}</Aviso>}
      <Tarjeta titulo="Personas e invitaciones">
        <ul className="divide-y text-sm">
          {personal.datos?.map((p) => (
            <li key={p.sub ?? p.email} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <span>
                <span className="font-medium">{p.nombre}</span>{p.sub === sesion.sub && <span className="text-neutral-500"> (tú)</span>}
                <span className="block text-xs text-neutral-500">{p.email}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className="text-xs text-neutral-600">{NOMBRE_ROL[p.rol]}</span>
                {p.invitacion ? <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-800">Invitación pendiente</span>
                  : <Insignia activo={p.estado === "activo"} textoInactivo="Archivado" />}
                {p.invitacion ? (
                  <Button type="button" size="sm" variant="outline"
                    onClick={() => void escribir(eliminar(localId, "invitaciones", idDeEmail(p.email)), () => personal.recargar())}>Cancelar invitación</Button>
                ) : (
                  <Button type="button" size="sm" variant="outline" onClick={() => setEditando(p)}>Editar</Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Tarjeta>
      {invitando && <FormularioInvitacion localId={localId} roles={rolesPermitidos} onCerrar={() => setInvitando(false)} onGuardado={() => void personal.recargar()} />}
      {editando && <FormularioPersona localId={localId} persona={editando} esUnoMismo={editando.sub === sesion.sub} roles={rolesPermitidos}
        onCerrar={() => setEditando(null)} onGuardado={() => void personal.recargar()} />}
    </div>
  )
}
