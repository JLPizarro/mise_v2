import { useState } from "react"
import { crear, editar } from "@/api/admin"
import type { Categoria, Producto } from "@/api/tipos"
import { Campo, FormDialog } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { useGuardar } from "@/hooks/useGuardar"
import { CATEGORIAS } from "@/lib/categorias"
import { aEntero } from "@/lib/dinero"
import { CLASE_INPUT } from "@/lib/estilos"

export interface Cuarto { cuarto_id: string; nombre: string; activo: boolean }
interface FilaModificador { modificador_id?: string; nombre: string; precio: string }

interface Props {
  localId: string
  producto: Producto | null
  cuartos: Cuarto[]
  onCerrar: () => void
  onGuardado: () => void
}

/** Crea o edita un producto. En `modificadores` (lista completa) los existentes conservan su `modificador_id`. */
export default function FormularioProducto({ localId, producto, cuartos, onCerrar, onGuardado }: Props) {
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState(producto?.nombre ?? "")
  const [categoria, setCategoria] = useState<Categoria>(producto?.categoria ?? "Fondos")
  const [precio, setPrecio] = useState(producto ? String(producto.precio) : "")
  const [cuartoId, setCuartoId] = useState(producto?.cuarto_id ?? cuartos.find((c) => c.activo)?.cuarto_id ?? "")
  const [activo, setActivo] = useState(producto?.activo ?? true)
  const [descripcion, setDescripcion] = useState(producto?.descripcion ?? "")
  const [mods, setMods] = useState<FilaModificador[]>(
    producto?.modificadores.map((m) => ({ modificador_id: m.modificador_id, nombre: m.nombre, precio: String(m.precio_adicional) })) ?? [],
  )

  const precioEntero = aEntero(precio)
  const valido = nombre.trim() !== "" && precioEntero !== null && cuartoId !== "" && mods.every((m) => m.nombre.trim() !== "")

  function enviar() {
    const cuerpo = {
      nombre: nombre.trim(), categoria, precio: precioEntero, cuarto_id: cuartoId, activo,
      descripcion: descripcion.trim() || undefined,
      modificadores: mods.map((m) => ({ modificador_id: m.modificador_id, nombre: m.nombre.trim(), precio_adicional: aEntero(m.precio) ?? 0 })),
    }
    const c = producto ? editar(localId, "productos", producto.producto_id, { ...cuerpo, descripcion: descripcion.trim() }) : crear(localId, "productos", cuerpo)
    void guardar(c, () => { onGuardado(); onCerrar() })
  }

  return (
    <FormDialog abierto titulo={producto ? "Editar producto" : "Nuevo producto"} guardando={guardando} puedeGuardar={valido}
      error={error} onGuardar={enviar} onCerrar={onCerrar}>
      <Campo etiqueta="Nombre"><input className={CLASE_INPUT} value={nombre} maxLength={120} onChange={(e) => setNombre(e.target.value)} /></Campo>
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo etiqueta="Categoría">
          <select className={CLASE_INPUT} value={categoria} onChange={(e) => setCategoria(e.target.value as Categoria)}>
            {CATEGORIAS.map((c) => <option key={c}>{c}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Precio (pesos)">
          <input className={CLASE_INPUT} inputMode="numeric" value={precio} onChange={(e) => setPrecio(e.target.value.replace(/\D/g, ""))} />
        </Campo>
      </div>
      <Campo etiqueta="Cuarto">
        <select className={CLASE_INPUT} value={cuartoId} onChange={(e) => setCuartoId(e.target.value)}>
          {cuartos.filter((c) => c.activo || c.cuarto_id === cuartoId).map((c) => <option key={c.cuarto_id} value={c.cuarto_id}>{c.nombre}</option>)}
        </select>
      </Campo>
      <Campo etiqueta="Descripción">
        <input className={CLASE_INPUT} value={descripcion} maxLength={300} onChange={(e) => setDescripcion(e.target.value)} />
      </Campo>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo</label>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Modificadores</p>
          <Button type="button" size="sm" variant="outline" onClick={() => setMods([...mods, { nombre: "", precio: "0" }])}>Agregar modificador</Button>
        </div>
        {mods.map((m, i) => (
          <div key={m.modificador_id ?? `nuevo-${i}`} className="flex gap-2">
            <input aria-label={`Nombre del modificador ${i + 1}`} className={CLASE_INPUT} placeholder="Nombre" value={m.nombre} maxLength={80}
              onChange={(e) => setMods(mods.map((x, j) => (j === i ? { ...x, nombre: e.target.value } : x)))} />
            <input aria-label={`Precio adicional del modificador ${i + 1}`} className={`${CLASE_INPUT} max-w-28`} inputMode="numeric" placeholder="+$" value={m.precio}
              onChange={(e) => setMods(mods.map((x, j) => (j === i ? { ...x, precio: e.target.value.replace(/\D/g, "") } : x)))} />
            <Button type="button" variant="outline" aria-label="Quitar modificador" onClick={() => setMods(mods.filter((_, j) => j !== i))}>✕</Button>
          </div>
        ))}
      </div>
    </FormDialog>
  )
}
