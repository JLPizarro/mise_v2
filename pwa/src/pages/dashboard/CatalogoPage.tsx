import { useMemo, useState } from "react"
import { editar } from "@/api/admin"
import type { Categoria, Producto } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import FormularioProducto, { type Cuarto } from "@/components/dashboard/FormularioProducto"
import { Insignia } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { useAdminLista } from "@/hooks/useAdmin"
import { useEscribir } from "@/hooks/useComando"
import { CATEGORIAS } from "@/lib/categorias"
import { pesos } from "@/lib/dinero"
import { useSesion } from "@/sesion/useSesion"

export default function CatalogoPage() {
  const { local } = useSesion()
  const localId = local!.local_id
  const escribir = useEscribir()
  const productos = useAdminLista<Producto>(localId, "productos")
  const cuartos = useAdminLista<Cuarto>(localId, "cuartos")
  const [categoria, setCategoria] = useState<Categoria | "todas">("todas")
  const [estado, setEstado] = useState<"todos" | "activos" | "inactivos">("todos")
  const [editando, setEditando] = useState<Producto | "nuevo" | null>(null)

  const filtrados = useMemo(
    () => (productos.datos ?? []).filter((p) =>
      (categoria === "todas" || p.categoria === categoria) &&
      (estado === "todos" || (estado === "activos") === p.activo)),
    [productos.datos, categoria, estado],
  )
  const nombreCuarto = (id: string) => cuartos.datos?.find((c) => c.cuarto_id === id)?.nombre ?? id

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Catálogo</h1>
        <Button type="button" onClick={() => setEditando("nuevo")} disabled={!cuartos.datos}>Nuevo producto</Button>
      </div>
      {productos.error && <Aviso tipo="error">{productos.error}</Aviso>}

      <div className="flex flex-wrap gap-3">
        <select aria-label="Filtrar por categoría" className="h-10 rounded-lg border bg-white px-3 text-sm" value={categoria} onChange={(e) => setCategoria(e.target.value as Categoria | "todas")}>
          <option value="todas">Todas las categorías</option>
          {CATEGORIAS.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select aria-label="Filtrar por estado" className="h-10 rounded-lg border bg-white px-3 text-sm" value={estado} onChange={(e) => setEstado(e.target.value as typeof estado)}>
          <option value="todos">Todos</option><option value="activos">Activos</option><option value="inactivos">Inactivos</option>
        </select>
      </div>

      {productos.datos === null ? <p className="text-sm text-neutral-500">Cargando…</p> : (
        <div className="overflow-x-auto rounded-2xl border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr><th className="px-3 py-2">Producto</th><th className="px-3 py-2">Categoría</th><th className="px-3 py-2">Cuarto</th><th className="px-3 py-2 text-right">Precio</th><th className="px-3 py-2">Estado</th><th /></tr>
            </thead>
            <tbody className="divide-y">
              {filtrados.map((p) => (
                <tr key={p.producto_id}>
                  <td className="px-3 py-2">{p.nombre}{p.modificadores.length > 0 && <span className="block text-xs text-neutral-500">{p.modificadores.map((m) => m.nombre).join(", ")}</span>}</td>
                  <td className="px-3 py-2">{p.categoria}</td>
                  <td className="px-3 py-2">{nombreCuarto(p.cuarto_id)}</td>
                  <td className="px-3 py-2 text-right">{pesos(p.precio)}</td>
                  <td className="px-3 py-2"><Insignia activo={p.activo} /></td>
                  <td className="space-x-2 px-3 py-2 text-right whitespace-nowrap">
                    <Button type="button" size="sm" variant="outline" onClick={() => setEditando(p)}>Editar</Button>
                    <Button type="button" size="sm" variant="ghost"
                      onClick={() => void escribir(editar(localId, "productos", p.producto_id, { activo: !p.activo }), () => productos.recargar())}>
                      {p.activo ? "Desactivar" : "Activar"}
                    </Button>
                  </td>
                </tr>
              ))}
              {filtrados.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-neutral-500">No hay productos con esos filtros.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {editando && cuartos.datos && (
        <FormularioProducto localId={localId} producto={editando === "nuevo" ? null : editando} cuartos={cuartos.datos}
          onCerrar={() => setEditando(null)} onGuardado={() => void productos.recargar()} />
      )}
    </div>
  )
}
