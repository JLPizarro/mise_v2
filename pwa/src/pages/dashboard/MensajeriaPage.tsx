import { useCallback, useEffect, useState } from "react"
import {
  catalogo as pedirCatalogo, crearDestino, crearRegla, descartarFallido, destinos as pedirDestinos, eliminarDestino,
  eliminarRegla, enviarPrueba, fallidos as pedirFallidos, mensajesDeDestino, reprocesarFallido,
  type Catalogo, type Destino, type Diagnostico, type Fallido, type ListaDestinos, type ListaFallidos, type MensajeDestino,
  type ResultadoPrueba, type TipoDestino,
} from "@/api/mensajeria"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import { Campo, FormDialog, Tarjeta } from "@/components/dashboard/ui"
import { Button } from "@/components/ui/button"
import { mensajeDeError, useEscribir } from "@/hooks/useComando"
import { useGuardar } from "@/hooks/useGuardar"
import { CLASE_INPUT } from "@/lib/estilos"
import { fechaHora } from "@/lib/fechas"
import { validarDestino } from "@/lib/mensajeria"
import { useSesion } from "@/sesion/useSesion"

type Pestana = "destinos" | "canales" | "fallidos"

const ESTADO_SUSCRIPCION: Record<string, { texto: string; clase: string }> = {
  activa: { texto: "Activa", clase: "bg-emerald-100 text-emerald-800" },
  pendiente_confirmacion: { texto: "Falta confirmar el correo", clase: "bg-amber-100 text-amber-900" },
  no_existe: { texto: "Suscripción inexistente", clase: "bg-red-100 text-red-800" },
  desconocido: { texto: "Estado desconocido", clase: "bg-neutral-200 text-neutral-700" },
}

/** Carga con reintento manual: `datos` null mientras carga; `error` si falló. */
function useCarga<T>(cargar: () => Promise<T>) {
  const [datos, setDatos] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const recargar = useCallback(async () => {
    try {
      setDatos(await cargar())
      setError(null)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [cargar])
  useEffect(() => {
    void recargar()
  }, [recargar])
  return { datos, error, recargar }
}

// --- destinos y reglas ------------------------------------------------------------------------------

function NuevoDestino({ localId, avisos, onCerrar, onCreado }: {
  localId: string; avisos: { id: string; titulo: string }[]; onCerrar: () => void; onCreado: () => void
}) {
  const { guardando, error, guardar } = useGuardar()
  const [nombre, setNombre] = useState("")
  const [tipo, setTipo] = useState<TipoDestino>("correo")
  const [correo, setCorreo] = useState("")
  const [elegidos, setElegidos] = useState<string[]>([])
  const [intentado, setIntentado] = useState(false)
  const errores = validarDestino({ nombre, tipo, correo, avisos: elegidos })
  const valido = Object.keys(errores).length === 0

  return (
    <FormDialog abierto titulo="Nuevo destino" guardando={guardando} error={error} etiquetaGuardar="Crear destino"
      descripcion="Un destino recibe los avisos que elijas (sus reglas de distribución), solo de este local."
      onCerrar={onCerrar}
      onGuardar={() => {
        setIntentado(true)
        if (!valido) return
        void guardar(crearDestino(localId, { nombre: nombre.trim(), tipo, ...(tipo === "correo" ? { correo: correo.trim() } : {}), avisos: elegidos }),
          () => onCreado())
      }}>
      <Campo etiqueta="Nombre" ayuda={intentado ? errores.nombre : undefined}>
        <input className={CLASE_INPUT} value={nombre} maxLength={60} onChange={(e) => setNombre(e.target.value)} placeholder="Ej.: Jefe de turno" />
      </Campo>
      <fieldset className="space-y-1 text-sm">
        <legend className="font-medium">Tipo de destino</legend>
        <label className="flex items-center gap-2"><input type="radio" checked={tipo === "correo"} onChange={() => setTipo("correo")} />
          Correo electrónico (recibe un email por cada aviso; hay que confirmarlo una vez)</label>
        <label className="flex items-center gap-2"><input type="radio" checked={tipo === "cola"} onChange={() => setTipo("cola")} />
          Cola (otro sistema la consume; aquí puedes ver lo que llegó)</label>
      </fieldset>
      {tipo === "correo" && (
        <Campo etiqueta="Correo" ayuda={intentado ? errores.correo : undefined}>
          <input type="email" className={CLASE_INPUT} value={correo} maxLength={254} onChange={(e) => setCorreo(e.target.value)} />
        </Campo>
      )}
      <fieldset className="space-y-1 text-sm">
        <legend className="font-medium">Reglas: avisos que recibe</legend>
        {avisos.map((a) => (
          <label key={a.id} className="flex items-center gap-2">
            <input type="checkbox" checked={elegidos.includes(a.id)}
              onChange={(e) => setElegidos((x) => (e.target.checked ? [...x, a.id] : x.filter((y) => y !== a.id)))} />
            {a.titulo}
          </label>
        ))}
        {intentado && errores.avisos && <span className="block text-xs text-red-700">{errores.avisos}</span>}
      </fieldset>
    </FormDialog>
  )
}

function MensajesDelDestino({ localId, destino, onCerrar }: { localId: string; destino: Destino; onCerrar: () => void }) {
  const cargar = useCallback(() => mensajesDeDestino(localId, destino.destino_id), [localId, destino.destino_id])
  const { datos, error, recargar } = useCarga(cargar)
  return (
    <FormDialog abierto titulo={`Mensajes en «${destino.nombre}»`} guardando={false} etiquetaGuardar="Actualizar"
      descripcion="Lo que llegó a la cola de este destino. Mirar no los consume." onCerrar={onCerrar} onGuardar={() => void recargar()}>
      {error && <Aviso tipo="error">{error}</Aviso>}
      {datos?.mensajes.length === 0 && <p className="text-sm text-neutral-500">Todavía no llega ningún mensaje.</p>}
      <ul className="space-y-2 text-sm">
        {datos?.mensajes.map((m: MensajeDestino) => (
          <li key={m.mensaje_id} className="rounded-lg border p-2">
            <div className="text-xs text-neutral-500">{m.enviado_en ? fechaHora(m.enviado_en) : ""} · aviso {m.atributos.aviso ?? "?"}
              {m.atributos.prueba === "si" ? " · prueba" : ""}</div>
            <p>{m.texto}</p>
          </li>
        ))}
      </ul>
    </FormDialog>
  )
}

function TarjetaDestino({ localId, destino, disponibles, onCambio }: {
  localId: string; destino: Destino; disponibles: { id: string; titulo: string }[]; onCambio: () => void
}) {
  const escribir = useEscribir()
  const notificar = useNotificar()
  const [nuevaRegla, setNuevaRegla] = useState("")
  const [viendo, setViendo] = useState(false)
  const estado = ESTADO_SUSCRIPCION[destino.estado ?? "desconocido"]
  const faltantes = disponibles.filter((a) => !destino.avisos.includes(a.id))

  return (
    <li className="space-y-3 rounded-xl border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium">{destino.nombre}</p>
          <p className="text-xs text-neutral-500">{destino.tipo === "correo" ? `Correo: ${destino.correo}` : `Cola: ${destino.cola}`}</p>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${estado.clase}`}>{estado.texto}</span>
      </div>
      {destino.estado === "pendiente_confirmacion" && (
        <Aviso>AWS envió un correo a {destino.correo}: hay que pulsar «Confirm subscription» para empezar a recibir avisos.</Aviso>
      )}
      <div className="flex flex-wrap gap-2">
        {destino.reglas.map((r) => (
          <span key={r.aviso} className="inline-flex items-center gap-1 rounded-full bg-neutral-100 px-3 py-1 text-xs">
            {r.titulo}
            <button type="button" aria-label={`Quitar la regla ${r.titulo}`} className="ml-1 text-neutral-500 hover:text-red-700"
              onClick={() => void escribir(eliminarRegla(localId, destino.destino_id, r.aviso), () => { notificar("Regla eliminada", "ok"); onCambio() })}>×</button>
          </span>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {faltantes.length > 0 && (
          <form className="flex gap-2" onSubmit={(e) => {
            e.preventDefault()
            if (!nuevaRegla) return
            void escribir(crearRegla(localId, destino.destino_id, nuevaRegla), () => { setNuevaRegla(""); notificar("Regla creada", "ok"); onCambio() })
          }}>
            <select aria-label="Aviso de la nueva regla" className={`${CLASE_INPUT} h-9`} value={nuevaRegla} onChange={(e) => setNuevaRegla(e.target.value)}>
              <option value="">Agregar regla…</option>
              {faltantes.map((a) => <option key={a.id} value={a.id}>{a.titulo}</option>)}
            </select>
            <Button type="submit" size="sm" disabled={!nuevaRegla}>Agregar</Button>
          </form>
        )}
        {destino.tipo === "cola" && <Button type="button" size="sm" variant="outline" onClick={() => setViendo(true)}>Ver mensajes</Button>}
        <Button type="button" size="sm" variant="outline" onClick={() => {
          if (!window.confirm(`¿Eliminar el destino «${destino.nombre}»? Dejará de recibir avisos.`)) return
          void escribir(eliminarDestino(localId, destino.destino_id), () => { notificar("Destino eliminado", "ok"); onCambio() })
        }}>Eliminar destino</Button>
      </div>
      {viendo && <MensajesDelDestino localId={localId} destino={destino} onCerrar={() => setViendo(false)} />}
    </li>
  )
}

function Prueba({ localId, avisos }: { localId: string; avisos: { id: string; titulo: string }[] }) {
  const { guardando, error, guardar } = useGuardar()
  const [aviso, setAviso] = useState(avisos[0]?.id ?? "")
  const [resultado, setResultado] = useState<ResultadoPrueba | null>(null)
  return (
    <Tarjeta titulo="Probar la distribución">
      <p className="text-sm text-neutral-600">Publica un aviso de prueba y muestra qué destinos deben recibirlo según sus reglas.</p>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => {
        e.preventDefault()
        void guardar<ResultadoPrueba>(enviarPrueba(localId, aviso), (r) => setResultado(r))
      }}>
        <select aria-label="Aviso de prueba" className={`${CLASE_INPUT} max-w-xs`} value={aviso} onChange={(e) => setAviso(e.target.value)}>
          {avisos.map((a) => <option key={a.id} value={a.id}>{a.titulo}</option>)}
        </select>
        <Button type="submit" className="h-11" disabled={guardando || !aviso}>Enviar aviso de prueba</Button>
      </form>
      {error && <Aviso tipo="error">{error}</Aviso>}
      {resultado && (
        <Aviso tipo="ok">
          <p>{resultado.explicacion}</p>
          <p className="mt-1 font-medium">{resultado.destinos_esperados.length === 0 ? "Ningún destino tiene esa regla."
            : `Deben recibirlo: ${resultado.destinos_esperados.map((d) => d.nombre).join(", ")}.`}</p>
        </Aviso>
      )}
    </Tarjeta>
  )
}

function Destinos({ localId }: { localId: string }) {
  const cargar = useCallback(() => pedirDestinos(localId), [localId])
  const { datos, error, recargar } = useCarga<ListaDestinos>(cargar)
  const [creando, setCreando] = useState(false)
  const notificar = useNotificar()
  return (
    <div className="space-y-6">
      <Tarjeta titulo="Destinos y reglas de distribución" acciones={
        <Button type="button" disabled={!datos || datos.destinos.length >= datos.limite} onClick={() => setCreando(true)}>Nuevo destino</Button>}>
        <p className="text-sm text-neutral-600">Cada destino recibe solo los avisos de sus reglas y solo de este local.
          Los canales del sistema (colas de documentos y contingencia) no se modifican aquí.</p>
        {error && <Aviso tipo="error">{error}</Aviso>}
        {datos && datos.destinos.length === 0 && <p className="text-sm text-neutral-500">No hay destinos. Crea uno para recibir avisos.</p>}
        <ul className="space-y-3">
          {datos?.destinos.map((d) => (
            <TarjetaDestino key={d.destino_id} localId={localId} destino={d} disponibles={datos.avisos_disponibles} onCambio={() => void recargar()} />
          ))}
        </ul>
        {datos && <p className="text-xs text-neutral-500">{datos.destinos.length} de {datos.limite} destinos.</p>}
      </Tarjeta>
      {datos && <Prueba localId={localId} avisos={datos.avisos_disponibles} />}
      {creando && datos && (
        <NuevoDestino localId={localId} avisos={datos.avisos_disponibles} onCerrar={() => setCreando(false)}
          onCreado={() => { setCreando(false); notificar("Destino creado", "ok"); void recargar() }} />
      )}
    </div>
  )
}

// --- canales y rutas ------------------------------------------------------------------------------------

const TIPO_CANAL: Record<string, string> = {
  flujo: "Flujo de eventos", cola: "Cola", cola_fallidos: "Cola de fallidos", tema: "Tema (distribución)", programado: "Regla programada",
}

function Canales({ localId }: { localId: string }) {
  const cargar = useCallback(() => pedirCatalogo(localId), [localId])
  const { datos, error, recargar } = useCarga<Catalogo>(cargar)
  return (
    <div className="space-y-6">
      {error && <Aviso tipo="error">{error}</Aviso>}
      <Tarjeta titulo="Canales del sistema" acciones={<Button type="button" variant="outline" size="sm" onClick={() => void recargar()}>Actualizar</Button>}>
        <p className="text-sm text-neutral-600">Definidos en un solo catálogo central. Están protegidos: se crean con el despliegue.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-neutral-500"><tr><th className="py-2 pr-3">Canal</th><th className="pr-3">Para qué</th><th className="pr-3">Quién envía → quién procesa</th><th className="pr-3">Si falla</th><th>Mensajes</th></tr></thead>
            <tbody className="divide-y">
              {datos?.canales.map((c) => (
                <tr key={c.id} className="align-top">
                  <td className="py-2 pr-3"><p className="font-medium">{c.nombre}</p><p className="text-xs text-neutral-500">{TIPO_CANAL[c.tipo]}{c.fifo ? " · en orden (FIFO)" : ""}</p></td>
                  <td className="pr-3">{c.proposito}</td>
                  <td className="pr-3">{c.productores.join(", ")} → {c.consumidores.join(", ")}</td>
                  <td className="pr-3">{c.tratamiento || (c.fallidos ? `Va a ${c.fallidos}` : "—")}</td>
                  <td>{c.estado ? (c.estado.no_existe ? "No existe" : `${c.estado.visibles} en espera · ${c.estado.en_proceso} en proceso`) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Tarjeta>
      <Tarjeta titulo="Rutas: qué evento va a dónde">
        <ul className="divide-y text-sm">
          {datos?.rutas.map((r, i) => (
            <li key={i} className="py-2"><span className="font-medium">{r.evento}</span> → {r.canal} → {r.consumidor}: {r.efecto}
              {r.condicion && <span className="text-neutral-500"> ({r.condicion})</span>}</li>
          ))}
        </ul>
      </Tarjeta>
      <Tarjeta titulo="Avisos">
        <ul className="divide-y text-sm">
          {datos?.avisos.map((a) => (
            <li key={a.id} className="py-2"><span className="font-medium">{a.titulo}</span> — {a.descripcion}
              <span className="text-neutral-500"> · {a.administrable ? "se distribuye a destinos" : "alerta técnica (solo equipo técnico)"}</span></li>
          ))}
        </ul>
      </Tarjeta>
    </div>
  )
}

// --- mensajes fallidos ---------------------------------------------------------------------------------

/** A quién le toca resolverlo, según el origen que registró el consumidor. */
const ORIGEN: Record<string, { texto: string; quien: string; clase: string }> = {
  proveedor: { texto: "Servicio externo", quien: "el proveedor no respondió: esperar o contactarlo", clase: "bg-amber-100 text-amber-900" },
  aws: { texto: "Infraestructura AWS", quien: "falló un servicio propio de AWS: lo revisa el equipo técnico", clase: "bg-blue-100 text-blue-900" },
  negocio: { texto: "Regla de negocio", quien: "una regla rechazó la operación", clase: "bg-neutral-200 text-neutral-800" },
  codigo: { texto: "Defecto del sistema", quien: "error no previsto: reportarlo al equipo técnico", clase: "bg-red-100 text-red-800" },
}

function OrigenFallo({ d }: { d: Diagnostico }) {
  const o = ORIGEN[d.origen ?? ""]
  if (!o) return null
  return <span title={o.quien} className={`rounded-full px-2 py-0.5 text-xs font-medium ${o.clase}`}>{o.texto}</span>
}


function Fallidos({ localId }: { localId: string }) {
  const cargar = useCallback(() => pedirFallidos(localId), [localId])
  const { datos, error, recargar } = useCarga<ListaFallidos>(cargar)
  const escribir = useEscribir()
  const notificar = useNotificar()

  const actuar = (f: Fallido, reprocesar: boolean) => {
    if (!reprocesar && !window.confirm("¿Descartar este mensaje? No se volverá a procesar.")) return
    void escribir(reprocesar ? reprocesarFallido(localId, f) : descartarFallido(localId, f), () => {
      notificar(reprocesar ? "Mensaje devuelto a su cola para procesarlo de nuevo" : "Mensaje descartado", "ok")
      void recargar()
    })
  }

  return (
    <div className="space-y-6">
      <Tarjeta titulo="Mensajes apartados" acciones={<Button type="button" variant="outline" size="sm" onClick={() => void recargar()}>Actualizar</Button>}>
        <p className="text-sm text-neutral-600">Mensajes que agotaron sus reintentos. Revisa el diagnóstico y decide: reprocesar (vuelve a su cola) o descartar.</p>
        {error && <Aviso tipo="error">{error}</Aviso>}
        {datos?.fallidos.length === 0 && <p className="text-sm text-neutral-500">No hay mensajes apartados.</p>}
        <ul className="space-y-3">
          {datos?.fallidos.map((f) => (
            <li key={f.mensaje_id} className="space-y-2 rounded-xl border p-3 text-sm">
              <p className="font-medium">{f.resumen}</p>
              <p className="text-xs text-neutral-500">{f.canal} · apartado en {f.cola_fallidos}{f.enviado_en ? ` · ${fechaHora(f.enviado_en)}` : ""}</p>
              {f.diagnostico ? (
                <Aviso tipo="error">
                  <div className="mb-1 flex flex-wrap items-center gap-2"><OrigenFallo d={f.diagnostico} />
                    <span className="text-xs">{ORIGEN[f.diagnostico.origen ?? ""]?.quien}</span></div>
                  Último error ({f.diagnostico.consumidor}, intento {f.diagnostico.intento}): {f.diagnostico.error_mensaje}
                </Aviso>
              ) : <p className="text-xs text-neutral-500">Sin diagnóstico registrado (revisar CloudWatch Logs con el id {f.mensaje_id}).</p>}
              <details><summary className="cursor-pointer text-xs text-neutral-600">Contenido del mensaje</summary>
                <pre className="mt-1 overflow-x-auto rounded bg-neutral-100 p-2 text-xs">{JSON.stringify(f.cuerpo, null, 2)}</pre></details>
              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={() => actuar(f, true)}>Reprocesar</Button>
                <Button type="button" size="sm" variant="outline" onClick={() => actuar(f, false)}>Descartar</Button>
              </div>
            </li>
          ))}
        </ul>
      </Tarjeta>
      <Tarjeta titulo="Errores recientes de los consumidores">
        {datos?.errores_recientes.length === 0 && <p className="text-sm text-neutral-500">Sin errores en los últimos 14 días.</p>}
        <ul className="divide-y text-sm">
          {datos?.errores_recientes.map((d, i) => (
            <li key={`${d.mensaje_id}-${i}`} className="py-2">
              <span className="flex flex-wrap items-center gap-2 text-xs text-neutral-500"><OrigenFallo d={d} />
                {fechaHora(d.registrado_en)} · {d.consumidor} · intento {d.intento}
                {d.recuperable ? " · se reintentará" : " · sin más reintentos"}</span>
              <p>{d.referencia}: {d.error_mensaje}</p>
            </li>
          ))}
        </ul>
      </Tarjeta>
    </div>
  )
}

export default function MensajeriaPage() {
  const { local } = useSesion()
  const localId = local!.local_id
  const [pestana, setPestana] = useState<Pestana>("destinos")
  const boton = (p: Pestana, texto: string) => (
    <button type="button" onClick={() => setPestana(p)}
      className={`min-h-11 rounded-lg px-3 text-sm font-medium ${pestana === p ? "bg-neutral-900 text-white" : "text-neutral-600 hover:bg-neutral-100"}`}>{texto}</button>
  )
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Mensajería</h1>
        <p className="text-sm text-neutral-600">Avisos en segundo plano: quién los recibe, qué canales los transportan y qué hacer con los que fallan.</p>
      </div>
      <div className="flex flex-wrap gap-2">{boton("destinos", "Destinos y reglas")}{boton("canales", "Canales y rutas")}{boton("fallidos", "Mensajes fallidos")}</div>
      {pestana === "destinos" && <Destinos localId={localId} />}
      {pestana === "canales" && <Canales localId={localId} />}
      {pestana === "fallidos" && <Fallidos localId={localId} />}
    </div>
  )
}
