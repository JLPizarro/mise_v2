import { useEffect, useState } from "react"
import { crear, editar, eliminar, listar } from "@/api/admin"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import { Campo, Tarjeta } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { useAdminLista } from "@/hooks/useAdmin"
import { mensajeDeError, useEscribir } from "@/hooks/useComando"
import { useGuardar } from "@/hooks/useGuardar"
import { aEntero } from "@/lib/dinero"
import { CLASE_INPUT } from "@/lib/estilos"
import { useSesion } from "@/sesion/useSesion"

interface ConfigLocal {
  nombre_local: string; marca: string; propina_sugerida_pct: number; umbral_diferencia_pct: number
  umbral_diferencia_minimo: number; impresora_caja_id?: string | null
}
interface Estacion { estacion_id: string; nombre: string }
interface Impresora { impresora_id: string; nombre: string }

/** El umbral es un porcentaje (no dinero): hasta 2 decimales. */
const aPorcentaje = (t: string): number | null => (/^\d+([.,]\d{1,2})?$/.test(t.trim()) ? Number(t.trim().replace(",", ".")) : null)

function DatosDelLocal({ localId, impresoras }: { localId: string; impresoras: Impresora[] }) {
  const { guardando, error, guardar } = useGuardar()
  const notificar = useNotificar()
  const [datos, setDatos] = useState<ConfigLocal | null>(null)
  const [cargaError, setCargaError] = useState<string | null>(null)
  const [nombre, setNombre] = useState("")
  const [marca, setMarca] = useState("")
  const [propina, setPropina] = useState("")
  const [umbral, setUmbral] = useState("")
  const [minimo, setMinimo] = useState("")
  const [impresoraCaja, setImpresoraCaja] = useState("")

  useEffect(() => {
    listar<ConfigLocal>(localId, "configuracion").then((c) => {
      setDatos(c)
      setNombre(c.nombre_local)
      setMarca(c.marca)
      setPropina(String(c.propina_sugerida_pct))
      setUmbral(String(c.umbral_diferencia_pct))
      setMinimo(String(c.umbral_diferencia_minimo))
      setImpresoraCaja(c.impresora_caja_id ?? "")
    }, (e: unknown) => setCargaError(mensajeDeError(e)))
  }, [localId])

  const p = aEntero(propina)
  const u = aPorcentaje(umbral)
  const m = aEntero(minimo)
  const valido = nombre.trim() !== "" && marca.trim() !== "" && p !== null && p <= 100 && u !== null && m !== null

  return (
    <Tarjeta titulo="Datos del local">
      {cargaError && <Aviso tipo="error">{cargaError}</Aviso>}
      {datos && (
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => {
          e.preventDefault()
          void guardar(editar(localId, "configuracion", "local", {
            nombre_local: nombre.trim(), marca: marca.trim(), propina_sugerida_pct: p, umbral_diferencia_pct: u,
            umbral_diferencia_minimo: m, impresora_caja_id: impresoraCaja || null,
          }), () => notificar("Configuración guardada", "ok"))
        }}>
          <Campo etiqueta="Nombre del local"><input className={CLASE_INPUT} value={nombre} maxLength={120} onChange={(e) => setNombre(e.target.value)} /></Campo>
          <Campo etiqueta="Marca"><input className={CLASE_INPUT} value={marca} maxLength={120} onChange={(e) => setMarca(e.target.value)} /></Campo>
          <Campo etiqueta="Propina sugerida (%)"><input className={CLASE_INPUT} inputMode="numeric" value={propina} onChange={(e) => setPropina(e.target.value.replace(/\D/g, ""))} /></Campo>
          <Campo etiqueta="Umbral de diferencia de caja (%)" ayuda="Hasta 2 decimales"><input className={CLASE_INPUT} inputMode="decimal" value={umbral} onChange={(e) => setUmbral(e.target.value)} /></Campo>
          <Campo etiqueta="Umbral mínimo (pesos)"><input className={CLASE_INPUT} inputMode="numeric" value={minimo} onChange={(e) => setMinimo(e.target.value.replace(/\D/g, ""))} /></Campo>
          <Campo etiqueta="Impresora de caja">
            <select className={CLASE_INPUT} value={impresoraCaja} onChange={(e) => setImpresoraCaja(e.target.value)}>
              <option value="">Sin impresora</option>
              {impresoras.map((i) => <option key={i.impresora_id} value={i.impresora_id}>{i.nombre}</option>)}
            </select>
          </Campo>
          {error && <div className="sm:col-span-2"><Aviso tipo="error">{error}</Aviso></div>}
          <div className="sm:col-span-2"><Button type="submit" className="h-11" disabled={guardando || !valido}>Guardar cambios</Button></div>
        </form>
      )}
    </Tarjeta>
  )
}

function Estaciones({ localId }: { localId: string }) {
  const estaciones = useAdminLista<Estacion>(localId, "estaciones")
  const escribir = useEscribir()
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState("")
  return (
    <Tarjeta titulo="Estaciones de caja">
      <p className="text-sm text-neutral-600">Un equipo registrado como estación puede seguir tomando comandas sin internet.</p>
      <ul className="divide-y text-sm">
        {estaciones.datos?.map((e) => (
          <li key={e.estacion_id} className="flex items-center justify-between py-2">
            <span>{e.nombre}</span>
            <Button type="button" size="sm" variant="outline" onClick={() => void escribir(eliminar(localId, "estaciones", e.estacion_id), () => estaciones.recargar())}>Eliminar</Button>
          </li>
        ))}
        {estaciones.datos?.length === 0 && <li className="py-2 text-neutral-500">No hay estaciones.</li>}
      </ul>
      <form className="flex gap-2" onSubmit={(ev) => {
        ev.preventDefault()
        void guardar(crear(localId, "estaciones", { nombre: nombre.trim() }), () => { setNombre(""); void estaciones.recargar() })
      }}>
        <input aria-label="Nombre de la estación" className={CLASE_INPUT} placeholder="Nombre de la nueva estación" value={nombre} maxLength={80} onChange={(e) => setNombre(e.target.value)} />
        <Button type="submit" className="h-11" disabled={guardando || nombre.trim() === ""}>Crear</Button>
      </form>
      {error && <Aviso tipo="error">{error}</Aviso>}
    </Tarjeta>
  )
}

function MiCodigo({ localId }: { localId: string }) {
  const { guardando, error, guardar } = useGuardar()
  const notificar = useNotificar()
  const [codigo, setCodigo] = useState("")
  return (
    <Tarjeta titulo="Mi código de autorización">
      <p className="text-sm text-neutral-600">Sirve para autorizar retiros de caja. De 4 a 8 dígitos.</p>
      <form className="flex gap-2" onSubmit={(e) => {
        e.preventDefault()
        const enviado = codigo
        setCodigo("")
        void guardar(crear(localId, "mi-codigo", { codigo: enviado }), () => notificar("Código actualizado", "ok"))
      }}>
        <input type="password" inputMode="numeric" autoComplete="new-password" aria-label="Código de autorización" className={CLASE_INPUT} maxLength={8}
          value={codigo} onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ""))} />
        <Button type="submit" className="h-11" disabled={guardando || codigo.length < 4}>Guardar</Button>
      </form>
      {error && <Aviso tipo="error">{error}</Aviso>}
    </Tarjeta>
  )
}

export default function ConfiguracionPage() {
  const { local } = useSesion()
  const localId = local!.local_id
  const impresoras = useAdminLista<Impresora>(localId, "impresoras")
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Configuración</h1>
      {impresoras.datos && <DatosDelLocal localId={localId} impresoras={impresoras.datos} />}
      <Estaciones localId={localId} />
      <MiCodigo localId={localId} />
    </div>
  )
}
