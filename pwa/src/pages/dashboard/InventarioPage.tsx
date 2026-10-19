import { useState } from "react"
import { crear, editar } from "@/api/admin"
import type { Producto, Unidad } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { Campo, FormDialog, Insignia, Tarjeta } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { useAdminLista } from "@/hooks/useAdmin"
import { useGuardar } from "@/hooks/useGuardar"
import { aDecimal, milesimas } from "@/lib/dinero"
import { CLASE_INPUT } from "@/lib/estilos"
import { useSesion } from "@/sesion/useSesion"

interface MateriaPrima { materia_prima_id: string; nombre: string; unidad: Unidad; stock_actual_mil: number; stock_minimo_mil: number; activo: boolean }
interface Receta { producto_id: string; ingredientes: { materia_prima_id: string; cantidad_mil: number }[] }
const UNIDADES: Unidad[] = ["kg", "g", "l", "ml", "unidad"]
const aTexto = (mil: number) => String(mil / 1000)

function FormularioMateriaPrima({ localId, materia, onCerrar, onGuardado }: { localId: string; materia: MateriaPrima | null; onCerrar: () => void; onGuardado: () => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState(materia?.nombre ?? "")
  const [unidad, setUnidad] = useState<Unidad>(materia?.unidad ?? "kg")
  const [actual, setActual] = useState(materia ? aTexto(materia.stock_actual_mil) : "0")
  const [minimo, setMinimo] = useState(materia ? aTexto(materia.stock_minimo_mil) : "0")
  const [activo, setActivo] = useState(materia?.activo ?? true)
  const a = aDecimal(actual)
  const m = aDecimal(minimo)
  return (
    <FormDialog abierto titulo={materia ? "Editar materia prima" : "Nueva materia prima"} guardando={guardando}
      puedeGuardar={nombre.trim() !== "" && a !== null && m !== null} error={error} onCerrar={onCerrar}
      onGuardar={() => {
        const cuerpo = { nombre: nombre.trim(), unidad, stock_actual: a, stock_minimo: m, activo }
        void guardar(materia ? editar(localId, "materias-primas", materia.materia_prima_id, cuerpo) : crear(localId, "materias-primas", cuerpo),
          () => { onGuardado(); onCerrar() })
      }}>
      <Campo etiqueta="Nombre"><input className={CLASE_INPUT} value={nombre} maxLength={120} onChange={(e) => setNombre(e.target.value)} /></Campo>
      <Campo etiqueta="Unidad">
        <select className={CLASE_INPUT} value={unidad} onChange={(e) => setUnidad(e.target.value as Unidad)}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select>
      </Campo>
      <div className="grid grid-cols-2 gap-3">
        <Campo etiqueta="Stock actual" ayuda="Hasta 3 decimales"><input className={CLASE_INPUT} inputMode="decimal" value={actual} onChange={(e) => setActual(e.target.value)} /></Campo>
        <Campo etiqueta="Stock mínimo" ayuda="Hasta 3 decimales"><input className={CLASE_INPUT} inputMode="decimal" value={minimo} onChange={(e) => setMinimo(e.target.value)} /></Campo>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo</label>
    </FormDialog>
  )
}

interface Fila { materia_prima_id: string; cantidad: string }

function FormularioReceta({ localId, producto, receta, materias, onCerrar, onGuardado }: { localId: string; producto: Producto; receta: Receta | undefined; materias: MateriaPrima[]; onCerrar: () => void; onGuardado: () => void }) {
  const { guardando, error, guardar } = useGuardar()
  const [filas, setFilas] = useState<Fila[]>(receta?.ingredientes.map((i) => ({ materia_prima_id: i.materia_prima_id, cantidad: aTexto(i.cantidad_mil) })) ?? [])
  const repetidas = new Set(filas.map((f) => f.materia_prima_id)).size !== filas.length
  const valida = filas.length >= 1 && filas.length <= 50 && !repetidas && filas.every((f) => f.materia_prima_id !== "" && (aDecimal(f.cantidad) ?? 0) > 0)
  return (
    <FormDialog abierto titulo={`Receta de ${producto.nombre}`} descripcion="De 1 a 50 ingredientes, sin repetir y con cantidad mayor que cero." guardando={guardando}
      puedeGuardar={valida} error={error} onCerrar={onCerrar}
      onGuardar={() => void guardar(
        editar(localId, "recetas", producto.producto_id, { ingredientes: filas.map((f) => ({ materia_prima_id: f.materia_prima_id, cantidad: aDecimal(f.cantidad) })) }),
        () => { onGuardado(); onCerrar() })}>
      {filas.map((f, i) => (
        <div key={i} className="flex gap-2">
          <select aria-label={`Ingrediente ${i + 1}`} className={CLASE_INPUT} value={f.materia_prima_id}
            onChange={(e) => setFilas(filas.map((x, j) => (j === i ? { ...x, materia_prima_id: e.target.value } : x)))}>
            <option value="">Elige una materia prima</option>
            {materias.map((m) => <option key={m.materia_prima_id} value={m.materia_prima_id}>{m.nombre} ({m.unidad})</option>)}
          </select>
          <input aria-label={`Cantidad ${i + 1}`} className={`${CLASE_INPUT} max-w-28`} inputMode="decimal" value={f.cantidad}
            onChange={(e) => setFilas(filas.map((x, j) => (j === i ? { ...x, cantidad: e.target.value } : x)))} />
          <Button type="button" variant="outline" aria-label="Quitar ingrediente" onClick={() => setFilas(filas.filter((_, j) => j !== i))}>✕</Button>
        </div>
      ))}
      {repetidas && <Aviso tipo="error">No repitas una materia prima.</Aviso>}
      <Button type="button" variant="outline" size="sm" onClick={() => setFilas([...filas, { materia_prima_id: "", cantidad: "" }])} disabled={filas.length >= 50}>Agregar ingrediente</Button>
    </FormDialog>
  )
}

export default function InventarioPage() {
  const { local } = useSesion()
  const localId = local!.local_id
  const materias = useAdminLista<MateriaPrima>(localId, "materias-primas")
  const recetas = useAdminLista<Receta>(localId, "recetas")
  const productos = useAdminLista<Producto>(localId, "productos")
  const [materia, setMateria] = useState<MateriaPrima | "nueva" | null>(null)
  const [receta, setReceta] = useState<Producto | null>(null)
  const nombreMateria = (id: string) => materias.datos?.find((m) => m.materia_prima_id === id)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Inventario</h1>
      {(materias.error ?? recetas.error) && <Aviso tipo="error">{materias.error ?? recetas.error}</Aviso>}
      <Tarjeta titulo="Materias primas" acciones={<Button type="button" size="sm" onClick={() => setMateria("nueva")}>Nueva materia prima</Button>}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-neutral-500"><tr><th className="py-2">Nombre</th><th className="text-right">Stock</th><th className="text-right">Mínimo</th><th className="pl-3">Estado</th><th /></tr></thead>
            <tbody className="divide-y">
              {materias.datos?.map((m) => {
                const bajo = m.stock_actual_mil < m.stock_minimo_mil
                return (
                  <tr key={m.materia_prima_id}>
                    <td className="py-2">{m.nombre}</td>
                    <td className={`text-right ${bajo ? "font-semibold text-red-700" : ""}`}>{milesimas(m.stock_actual_mil)} {m.unidad}{bajo && " ⚠ bajo el mínimo"}</td>
                    <td className="text-right">{milesimas(m.stock_minimo_mil)} {m.unidad}</td>
                    <td className="pl-3"><Insignia activo={m.activo} /></td>
                    <td className="text-right"><Button type="button" size="sm" variant="outline" onClick={() => setMateria(m)}>Editar</Button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Tarjeta>

      <Tarjeta titulo="Recetas por producto">
        <ul className="divide-y text-sm">
          {productos.datos?.map((p) => {
            const r = recetas.datos?.find((x) => x.producto_id === p.producto_id)
            return (
              <li key={p.producto_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>{p.nombre}
                  <span className="block text-xs text-neutral-500">
                    {r ? r.ingredientes.map((i) => `${nombreMateria(i.materia_prima_id)?.nombre ?? i.materia_prima_id} ${milesimas(i.cantidad_mil)}`).join(", ") : "Sin receta"}
                  </span>
                </span>
                <Button type="button" size="sm" variant="outline" disabled={!materias.datos?.length} onClick={() => setReceta(p)}>{r ? "Editar receta" : "Crear receta"}</Button>
              </li>
            )
          })}
        </ul>
      </Tarjeta>

      {materia && <FormularioMateriaPrima localId={localId} materia={materia === "nueva" ? null : materia} onCerrar={() => setMateria(null)} onGuardado={() => void materias.recargar()} />}
      {receta && materias.datos && (
        <FormularioReceta localId={localId} producto={receta} receta={recetas.datos?.find((x) => x.producto_id === receta.producto_id)} materias={materias.datos.filter((m) => m.activo)}
          onCerrar={() => setReceta(null)} onGuardado={() => void recetas.recargar()} />
      )}
    </div>
  )
}
