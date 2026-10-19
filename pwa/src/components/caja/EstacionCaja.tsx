import { useCallback, useEffect, useState } from "react"
import { listar } from "@/api/admin"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import { Button } from "@/components/ui/button"
import { useEstacion } from "@/hooks/useEstacion"
import { mensajeDeError } from "@/hooks/useComando"
import { hora } from "@/lib/fechas"
import { nombreOperacion } from "@/lib/operaciones"
import { cola } from "@/offline/cola"
import { activarEstacion, desactivarEstacion } from "@/offline/estacion"
import type { Guardado, Rechazado } from "@/offline/db"
import { vaciarCola } from "@/offline/sincronizar"
import { puede } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

/** Registrar este equipo como PC de caja: habilita la cola local (P13). Dueño, admin y cajero. */
export default function EstacionCaja({ localId }: { localId: string }) {
  const { local, rol, sesion } = useSesion()
  const notificar = useNotificar()
  const estacion = useEstacion(localId)
  const [nombres, setNombres] = useState<Record<string, string>>({})
  const [guardadas, setGuardadas] = useState<Guardado[]>([])
  const [rechazadas, setRechazadas] = useState<Rechazado[]>([])
  const [enviando, setEnviando] = useState(false)

  const leerCola = useCallback(async () => {
    setGuardadas(await cola.pendientes(localId))
    setRechazadas(await cola.rechazados(localId))
  }, [localId])

  useEffect(() => {
    if (estacion === null) return
    void leerCola()
    return cola.suscribir(() => void leerCola())
  }, [estacion, leerCola])

  useEffect(() => {
    if (!puede(rol, ["dueno", "admin"])) return
    listar<{ estaciones: { estacion_id: string; nombre: string }[] }>(localId, "estaciones").then(
      (r) => setNombres(Object.fromEntries(r.estaciones.map((e) => [e.estacion_id, e.nombre]))),
      () => undefined,
    )
  }, [localId, rol])

  if (!local || !puede(rol, ["dueno", "admin", "cajero"])) return <Aviso>Esta sección es solo para caja.</Aviso>
  const nombre = (id: string) => nombres[id] ?? id

  async function enviarAhora() {
    setEnviando(true)
    try {
      const n = await vaciarCola(localId)
      notificar(n > 0 ? `${n} comandas enviadas a la nube` : "No se envió nada: ingresa con Google y revisa la conexión.", n > 0 ? "ok" : "info")
      await leerCola()
    } finally {
      setEnviando(false)
    }
  }

  if (estacion === null) {
    return (
      <section className="space-y-3">
        <p className="text-sm text-neutral-600">Este equipo no es una estación de caja. Registrarlo permite seguir tomando comandas sin internet.</p>
        {local.estaciones_caja.length === 0 && <Aviso>El local no tiene estaciones de caja. Pide a un administrador que cree una.</Aviso>}
        <ul className="space-y-2">
          {local.estaciones_caja.map((id) => (
            <li key={id}>
              <Button type="button" variant="outline" className="h-11 w-full justify-start"
                onClick={() => void activarEstacion(localId, id, { local, sub: sesion.sub, nombre: sesion.nombre }).then(() => notificar(`Este equipo ahora es ${nombre(id)}`, "ok"))}>
                Usar este equipo como {nombre(id)}
              </Button>
            </li>
          ))}
        </ul>
      </section>
    )
  }

  return (
    <section className="space-y-5">
      <div className="rounded-2xl border bg-white p-4 text-sm">
        <p className="font-semibold">Este equipo es {nombre(estacion)}</p>
        <p className="text-neutral-600">Sin internet, las comandas se guardan aquí y se envían cuando vuelva la conexión.</p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Comandas guardadas ({guardadas.length})</h3>
          <Button type="button" size="sm" disabled={enviando || guardadas.length === 0} onClick={() => void enviarAhora()}>Enviar ahora</Button>
        </div>
        {guardadas.length === 0 ? <p className="text-sm text-neutral-500">No hay comandas guardadas.</p> : (
          <ul className="divide-y rounded-2xl border bg-white text-sm">
            {guardadas.map((g) => (
              <li key={g.id} className="flex justify-between gap-3 px-4 py-2">
                <span>{nombreOperacion(g.operacion ?? "")}{g.mesaId && ` · mesa ${g.mesaId}`}</span>
                <span className="text-xs text-neutral-500">{hora(g.creadoEn)} · {g.registradoPor.nombre || "—"}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {rechazadas.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-semibold">Rechazadas al enviar</h3>
          <ul className="space-y-2">
            {rechazadas.map((r) => (
              <li key={r.id} className="flex items-start justify-between gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm">
                <span>{nombreOperacion(r.operacion ?? "")}{r.mesaId && ` · mesa ${r.mesaId}`}<span className="block text-red-800">{r.mensaje}</span></span>
                <Button type="button" size="sm" variant="outline" onClick={() => void cola.descartarRechazado(r.id).then(leerCola)}>Descartar</Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Button type="button" variant="outline"
        onClick={() => void desactivarEstacion(localId).then(() => notificar("Este equipo ya no es una estación", "ok"), (e: unknown) => notificar(mensajeDeError(e), "error"))}>
        Dejar de usar este equipo como estación
      </Button>
    </section>
  )
}
