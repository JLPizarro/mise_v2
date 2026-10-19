import { useCallback, useEffect, useState } from "react"
import { conflictos as pedirConflictos, resolverConflicto } from "@/api/caja"
import type { Conflicto } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { Button } from "@/components/ui/button"
import { mensajeDeError, useEscribir } from "@/hooks/useComando"
import { fechaHora } from "@/lib/fechas"
import { nombreOperacion } from "@/lib/operaciones"

function TarjetaConflicto({ c, onResolver }: { c: Conflicto; onResolver: (resolucion: "resuelto" | "descartado", nota: string) => void }) {
  const [nota, setNota] = useState("")
  const mesa = typeof c.comando.cuerpo.mesa_id === "string" ? c.comando.cuerpo.mesa_id : null
  return (
    <li className="space-y-2 rounded-2xl border bg-white p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{nombreOperacion(c.operacion)}{mesa && ` · mesa ${mesa}`}</p>
        <span className={`rounded-full px-2 py-0.5 text-xs ${c.estado === "abierto" ? "bg-amber-100 text-amber-800" : "bg-neutral-100 text-neutral-600"}`}>
          {c.estado === "abierto" ? "Abierto" : c.estado === "resuelto" ? "Resuelto" : "Descartado"}
        </span>
      </div>
      <p>{c.motivo}</p>
      <p className="text-xs text-neutral-500">{c.comando.nombre || "—"} · {fechaHora(c.comando.ocurrido_en)}</p>
      {c.nota && <p className="text-xs text-neutral-600">Nota: {c.nota}</p>}
      {c.estado === "abierto" && (
        <div className="space-y-2 pt-1">
          <input value={nota} maxLength={500} onChange={(e) => setNota(e.target.value)} placeholder="Nota (opcional)"
            aria-label="Nota" className="h-10 w-full rounded-lg border px-3" />
          <div className="flex gap-2">
            <Button type="button" size="sm" onClick={() => onResolver("resuelto", nota)}>Marcar resuelto</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onResolver("descartado", nota)}>Descartar</Button>
          </div>
        </div>
      )}
    </li>
  )
}

export default function ConflictosCaja({ localId }: { localId: string }) {
  const escribir = useEscribir()
  const [todos, setTodos] = useState(false)
  const [lista, setLista] = useState<Conflicto[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setLista((await pedirConflictos(localId, todos)).conflictos)
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [localId, todos])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={todos} onChange={(e) => setTodos(e.target.checked)} /> Ver resueltos
      </label>
      {error && <Aviso tipo="error">{error}</Aviso>}
      {lista === null && !error && <p className="text-sm text-neutral-500">Cargando…</p>}
      {lista?.length === 0 && <p className="text-sm text-neutral-500">No hay conflictos.</p>}
      <ul className="space-y-3">
        {lista?.map((c) => (
          <TarjetaConflicto key={c.conflicto_id} c={c}
            onResolver={(resolucion, nota) => void escribir(resolverConflicto(localId, c.conflicto_id, resolucion, nota.trim()), () => void cargar())} />
        ))}
      </ul>
    </div>
  )
}
