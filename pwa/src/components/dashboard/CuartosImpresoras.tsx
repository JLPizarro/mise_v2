import { useState } from "react"
import { accion, crear, editar } from "@/api/admin"
import { Campo, FormDialog, Insignia, Tarjeta } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { config } from "@/config"
import { useAdminLista } from "@/hooks/useAdmin"
import { useEscribir } from "@/hooks/useComando"
import { useGuardar } from "@/hooks/useGuardar"
import { CLASE_INPUT } from "@/lib/estilos"
import { useSesion } from "@/sesion/useSesion"

interface Cuarto { cuarto_id: string; nombre: string; descripcion: string; activo: boolean; impresora_id?: string | null }
interface Impresora { impresora_id: string; nombre: string; modelo: string; protocolo: string; activa: boolean }
interface ClaveImpresora extends Impresora { clave: string; usuario_cloudprnt: string }

function FormularioCuarto({ localId, cuarto, impresoras, onCerrar, onGuardado }: { localId: string; cuarto: Cuarto | null; impresoras: Impresora[]; onCerrar: () => void; onGuardado: () => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState(cuarto?.nombre ?? "")
  const [descripcion, setDescripcion] = useState(cuarto?.descripcion ?? "")
  const [activo, setActivo] = useState(cuarto?.activo ?? true)
  const [impresoraId, setImpresoraId] = useState(cuarto?.impresora_id ?? "")
  return (
    <FormDialog abierto titulo={cuarto ? "Editar cuarto" : "Nuevo cuarto"} guardando={guardando} puedeGuardar={nombre.trim() !== ""} error={error} onCerrar={onCerrar}
      onGuardar={() => void guardar(
        cuarto
          ? editar(localId, "cuartos", cuarto.cuarto_id, { nombre: nombre.trim(), descripcion: descripcion.trim(), activo, impresora_id: impresoraId || null })
          : crear(localId, "cuartos", { nombre: nombre.trim(), descripcion: descripcion.trim() || undefined, activo, impresora_id: impresoraId || undefined }),
        () => { onGuardado(); onCerrar() })}>
      <Campo etiqueta="Nombre"><input className={CLASE_INPUT} value={nombre} maxLength={80} onChange={(e) => setNombre(e.target.value)} /></Campo>
      <Campo etiqueta="Descripción"><input className={CLASE_INPUT} value={descripcion} maxLength={200} onChange={(e) => setDescripcion(e.target.value)} /></Campo>
      <Campo etiqueta="Impresora">
        <select className={CLASE_INPUT} value={impresoraId} onChange={(e) => setImpresoraId(e.target.value)}>
          <option value="">Sin impresora</option>
          {impresoras.map((i) => <option key={i.impresora_id} value={i.impresora_id}>{i.nombre}{i.activa ? "" : " (inactiva)"}</option>)}
        </select>
      </Campo>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo</label>
    </FormDialog>
  )
}

function FormularioImpresora({ localId, impresora, onCerrar, onGuardado, onClave }: { localId: string; impresora: Impresora | null; onCerrar: () => void; onGuardado: () => void; onClave: (c: ClaveImpresora) => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState(impresora?.nombre ?? "")
  const [modelo, setModelo] = useState(impresora?.modelo ?? "")
  const [activa, setActiva] = useState(impresora?.activa ?? true)
  return (
    <FormDialog abierto titulo={impresora ? "Editar impresora" : "Nueva impresora"} guardando={guardando} puedeGuardar={nombre.trim() !== ""} error={error} onCerrar={onCerrar}
      onGuardar={() => void guardar<ClaveImpresora | Impresora>(
        impresora
          ? editar(localId, "impresoras", impresora.impresora_id, { nombre: nombre.trim(), modelo: modelo.trim() || undefined, activa })
          : crear(localId, "impresoras", { nombre: nombre.trim(), modelo: modelo.trim() || undefined, activa }),
        (r) => {
          onGuardado()
          onCerrar()
          if ("clave" in r) onClave(r)
        })}>
      <Campo etiqueta="Nombre"><input className={CLASE_INPUT} value={nombre} maxLength={80} onChange={(e) => setNombre(e.target.value)} /></Campo>
      <Campo etiqueta="Modelo"><input className={CLASE_INPUT} value={modelo} maxLength={80} onChange={(e) => setModelo(e.target.value)} /></Campo>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activa} onChange={(e) => setActiva(e.target.checked)} /> Activa</label>
    </FormDialog>
  )
}

/** La clave se muestra una sola vez: el servidor no la vuelve a entregar. */
function DialogoClave({ datos, tenantId, localId, onCerrar }: { datos: ClaveImpresora; tenantId: string; localId: string; onCerrar: () => void }) {
  const url = `${config().api_url}/impresion/${tenantId}/${localId}/${datos.impresora_id}`
  return (
    <Dialog open onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Datos de la impresora {datos.nombre}</DialogTitle>
          <DialogDescription>Copia estos datos ahora; la clave no se volverá a mostrar.</DialogDescription>
        </DialogHeader>
        <dl className="space-y-2 text-sm">
          <div><dt className="font-medium">Usuario</dt><dd className="break-all rounded bg-neutral-100 p-2 font-mono">{datos.usuario_cloudprnt}</dd></div>
          <div><dt className="font-medium">Clave</dt><dd className="break-all rounded bg-neutral-100 p-2 font-mono">{datos.clave}</dd></div>
          <div><dt className="font-medium">URL CloudPRNT</dt><dd className="break-all rounded bg-neutral-100 p-2 font-mono">{url}</dd></div>
        </dl>
        <DialogFooter><Button type="button" onClick={onCerrar}>Ya los copié</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Cuartos (cocina, barra…) e impresoras CloudPRNT. No hay borrado: se desactivan. */
export default function CuartosImpresoras({ localId }: { localId: string }) {
  const { local } = useSesion()
  const escribir = useEscribir()
  const cuartos = useAdminLista<Cuarto>(localId, "cuartos")
  const impresoras = useAdminLista<Impresora>(localId, "impresoras")
  const [cuarto, setCuarto] = useState<Cuarto | "nuevo" | null>(null)
  const [impresora, setImpresora] = useState<Impresora | "nueva" | null>(null)
  const [clave, setClave] = useState<ClaveImpresora | null>(null)
  const nombreImpresora = (id?: string | null) => impresoras.datos?.find((i) => i.impresora_id === id)?.nombre

  return (
    <div className="space-y-4">
      <Tarjeta titulo="Cuartos" acciones={<Button type="button" size="sm" disabled={!impresoras.datos} onClick={() => setCuarto("nuevo")}>Nuevo cuarto</Button>}>
        <ul className="divide-y text-sm">
          {cuartos.datos?.map((c) => (
            <li key={c.cuarto_id} className="flex items-center justify-between gap-2 py-2">
              <span className="flex flex-wrap items-center gap-2">{c.nombre} <Insignia activo={c.activo} />
                <span className="text-xs text-neutral-500">{nombreImpresora(c.impresora_id) ? `Impresora: ${nombreImpresora(c.impresora_id)}` : "Sin impresora"}</span></span>
              <Button type="button" size="sm" variant="outline" onClick={() => setCuarto(c)}>Editar</Button>
            </li>
          ))}
        </ul>
      </Tarjeta>
      <Tarjeta titulo="Impresoras" acciones={<Button type="button" size="sm" onClick={() => setImpresora("nueva")}>Nueva impresora</Button>}>
        <ul className="divide-y text-sm">
          {impresoras.datos?.map((i) => (
            <li key={i.impresora_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="flex items-center gap-2">{i.nombre} <span className="text-xs text-neutral-500">{i.modelo}</span> <Insignia activo={i.activa} textoActivo="Activa" textoInactivo="Inactiva" /></span>
              <span className="flex gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => setImpresora(i)}>Editar</Button>
                <Button type="button" size="sm" variant="ghost"
                  onClick={() => void escribir<ClaveImpresora>(accion(localId, "impresoras", i.impresora_id, "rotar-clave"), (r) => setClave(r))}>
                  Rotar clave
                </Button>
              </span>
            </li>
          ))}
        </ul>
      </Tarjeta>
      {cuarto && impresoras.datos && <FormularioCuarto localId={localId} cuarto={cuarto === "nuevo" ? null : cuarto} impresoras={impresoras.datos} onCerrar={() => setCuarto(null)} onGuardado={() => void cuartos.recargar()} />}
      {impresora && <FormularioImpresora localId={localId} impresora={impresora === "nueva" ? null : impresora} onCerrar={() => setImpresora(null)}
        onGuardado={() => { void impresoras.recargar(); void cuartos.recargar() }} onClave={setClave} />}
      {clave && local && <DialogoClave datos={clave} tenantId={local.tenant_id} localId={localId} onCerrar={() => setClave(null)} />}
    </div>
  )
}
