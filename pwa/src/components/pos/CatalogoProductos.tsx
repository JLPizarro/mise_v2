import type { Categoria, Producto } from "@/api/tipos"
import { CATEGORIAS } from "@/lib/categorias"
import { pesos } from "@/lib/dinero"

interface Props {
  categoria: Categoria
  productos: Producto[]
  cargada: boolean
  onCategoria: (categoria: Categoria) => void
  onProducto: (producto: Producto) => void
}

export default function CatalogoProductos({ categoria, productos, cargada, onCategoria, onProducto }: Props) {
  return (
    <section>
      <div className="mb-4">
        <h2 className="text-xl font-semibold">Agregar productos</h2>
        <p className="mt-1 text-sm text-neutral-500">Selecciona productos para agregarlos a la comanda.</p>
      </div>

      <div className="mb-4 flex gap-2 overflow-x-auto pb-2">
        {CATEGORIAS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onCategoria(c)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium ${
              categoria === c ? "bg-neutral-950 text-white" : "border bg-white text-neutral-700"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {!cargada && <p className="text-sm text-neutral-500">Cargando la carta…</p>}
      {cargada && productos.length === 0 && <p className="text-sm text-neutral-500">No hay productos en esta categoría.</p>}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {productos.map((p) => (
          <button
            key={p.producto_id}
            type="button"
            onClick={() => onProducto(p)}
            className="min-h-28 rounded-2xl border bg-white p-4 text-left transition hover:shadow-md active:scale-[0.98]"
          >
            <h3 className="font-semibold">{p.nombre}</h3>
            <p className="mt-2 text-lg font-medium">{pesos(p.precio)}</p>
          </button>
        ))}
      </div>
    </section>
  )
}
