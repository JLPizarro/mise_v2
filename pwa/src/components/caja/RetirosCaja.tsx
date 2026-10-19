import { useCallback, useEffect, useState } from "react"
import { autorizadores as pedirAutorizadores, registrarRetiro, retiros as pedirRetiros } from "@/api/caja"
import { ErrorApi } from "@/api/cliente"
import type { Autorizador, Retiro } from "@/api/tipos"
import AutorizacionAdmin from "@/components/caja/AutorizacionAdmin"
import { Aviso } from "@/components/comun/Aviso"
import { CampoPesos } from "@/components/comun/CampoPesos"
import { Button } from "@/components/ui/button"
import { mensajeDeError, useEscribir } from "@/hooks/useComando"
import { aEntero, pesos } from "@/lib/dinero"
import { fechaHora } from "@/lib/fechas"

export default function RetirosCaja({ localId }: { localId: string }) {
  const escribir = useEscribir()
  const [lista, setLista] = useState<Retiro[] | null>(null)
  const [sinTurno, setSinTurno] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autorizadores, setAutorizadores] = useState<Autorizador[]>([])
  const [monto, setMonto] = useState("")
  const [motivo, setMotivo] = useState("")
  const [autorizadorId, setAutorizadorId] = useState("")
  const [codigo, setCodigo] = useState("")
  const [errorEnvio, setErrorEnvio] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setLista((await pedirRetiros(localId)).retiros)
      setSinTurno(false)
      setError(null)
    } catch (e) {
      if (e instanceof ErrorApi && e.codigo === "TURNO_NO_ABIERTO") setSinTurno(true)
      else setError(mensajeDeError(e))
    }
  }, [localId])

  useEffect(() => {
    void cargar()
    pedirAutorizadores(localId).then((r) => setAutorizadores(r.autorizadores), () => setAutorizadores([]))
  }, [cargar, localId])

  const montoEntero = aEntero(monto)
  const listo = montoEntero !== null && montoEntero > 0 && motivo.trim() !== "" && autorizadorId !== "" && codigo.length >= 4

  async function enviar() {
    setOcupado(true)
    setErrorEnvio(null)
    const codigoEnviado = codigo
    setCodigo("") // el código nunca queda en pantalla después de enviar
    try {
      const r = await escribir<Retiro>(
        registrarRetiro(localId, { monto: montoEntero as number, motivo: motivo.trim(), autorizador_id: autorizadorId, codigo: codigoEnviado }),
        undefined,
        (e) => {
          if (e instanceof ErrorApi && e.codigo === "CODIGO_AUTORIZACION_INVALIDO") {
            setErrorEnvio(`Código incorrecto. Te quedan ${String(e.detalle.intentos_restantes ?? "algunos")} intentos`)
            return true
          }
          if (e instanceof ErrorApi) {
            setErrorEnvio(e.message)
            return true
          }
          return false
        },
      )
      if (r) {
        setMonto("")
        setMotivo("")
        void cargar()
      }
    } finally {
      setOcupado(false)
    }
  }

  if (sinTurno) return <Aviso>Sin turno abierto</Aviso>

  return (
    <div className="space-y-6">
      {error && <Aviso tipo="error">{error}</Aviso>}
      <section className="space-y-4 rounded-2xl border bg-white p-4">
        <h3 className="font-semibold">Nuevo retiro</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <CampoPesos etiqueta="Monto" valor={monto} onCambio={setMonto} />
          <label className="block space-y-1 text-sm">
            <span className="font-medium">Motivo</span>
            <input value={motivo} maxLength={200} onChange={(e) => setMotivo(e.target.value)} className="h-11 w-full rounded-lg border px-3" />
          </label>
        </div>
        <AutorizacionAdmin autorizadores={autorizadores} autorizadorId={autorizadorId} codigo={codigo}
          onAutorizador={setAutorizadorId} onCodigo={setCodigo} />
        {errorEnvio && <Aviso tipo="error">{errorEnvio}</Aviso>}
        <Button type="button" className="h-11" disabled={ocupado || !listo} onClick={() => void enviar()}>Registrar retiro</Button>
      </section>

      <section>
        <h3 className="mb-2 font-semibold">Retiros del turno</h3>
        {lista === null ? <p className="text-sm text-neutral-500">Cargando…</p>
          : lista.length === 0 ? <p className="text-sm text-neutral-500">Aún no hay retiros.</p>
          : (
            <ul className="divide-y rounded-2xl border bg-white text-sm">
              {lista.map((r) => (
                <li key={r.retiro_id} className="flex justify-between gap-3 px-4 py-3">
                  <span>{r.motivo}<span className="block text-xs text-neutral-500">{fechaHora(r.creado_en)}</span></span>
                  <span className="font-medium">{pesos(r.monto)}</span>
                </li>
              ))}
            </ul>
          )}
      </section>
    </div>
  )
}
