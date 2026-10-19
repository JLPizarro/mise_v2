import { useState } from "react"
import { abrirTurno, cerrarTurno, conciliacion, conteo } from "@/api/caja"
import type { ResultadoCierre, Turno } from "@/api/tipos"
import { Aviso } from "@/components/comun/Aviso"
import { useNotificar } from "@/components/comun/avisos"
import { CampoPesos } from "@/components/comun/CampoPesos"
import { Button } from "@/components/ui/button"
import { useEscribir } from "@/hooks/useComando"
import { fechaHora } from "@/lib/fechas"
import { aEntero, pesos } from "@/lib/dinero"

interface Props { localId: string; turno: Turno | null; onCambio: () => void }

const conteoCompleto = (t: Turno): boolean => t.primer_conteo !== null && (!t.requiere_segundo_conteo || t.segundo_conteo !== null)

function Paso({ numero, titulo, hecho, children }: { numero: number; titulo: string; hecho: boolean; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-2xl border bg-white p-4">
      <h3 className="flex items-center gap-2 font-semibold">
        <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${hecho ? "bg-emerald-600 text-white" : "bg-neutral-200"}`}>{hecho ? "✓" : numero}</span>
        {titulo}
      </h3>
      {children}
    </section>
  )
}

function Resultado({ r }: { r: ResultadoCierre }) {
  return (
    <section className="space-y-2 rounded-2xl border bg-white p-4 text-sm">
      <h3 className="text-lg font-semibold">Turno cerrado</h3>
      {r.fuera_de_umbral && <Aviso tipo="error">La diferencia de efectivo está fuera del umbral permitido ({pesos(r.umbral)}).</Aviso>}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
        <dt>Efectivo esperado</dt><dd className="text-right">{pesos(r.efectivo_esperado)}</dd>
        <dt>Conteo definitivo</dt><dd className="text-right">{pesos(r.conteo_definitivo)}</dd>
        <dt className="font-medium">Diferencia</dt><dd className="text-right font-medium">{pesos(r.diferencia_efectivo)}</dd>
        <dt>Efectivo (MISE)</dt><dd className="text-right">{pesos(r.total_efectivo_mise)}</dd>
        <dt>Débito (MISE)</dt><dd className="text-right">{pesos(r.total_debito_mise)}</dd>
        <dt>Crédito (MISE)</dt><dd className="text-right">{pesos(r.total_credito_mise)}</dd>
        <dt>Transferencia (MISE)</dt><dd className="text-right">{pesos(r.total_transferencia_mise)}</dd>
        <dt>Retiros</dt><dd className="text-right">{pesos(r.total_retiros)}</dd>
        <dt>Ventas</dt><dd className="text-right">{r.n_ventas} · {pesos(r.total_ventas)}</dd>
      </dl>
    </section>
  )
}

/** Turno de caja: apertura, arqueo ciego (1 o 2 conteos), conciliación del terminal y cierre. */
export default function CierreCaja({ localId, turno, onCambio }: Props) {
  const escribir = useEscribir()
  const notificar = useNotificar()
  const [apertura, setApertura] = useState("")
  const [conteoTexto, setConteoTexto] = useState("")
  const [debito, setDebito] = useState(turno?.conciliacion ? String(turno.conciliacion.total_debito_pos) : "")
  const [credito, setCredito] = useState(turno?.conciliacion ? String(turno.conciliacion.total_credito_pos) : "")
  const [notas, setNotas] = useState(turno?.conciliacion ? String(turno.conciliacion.total_notas_credito_pos) : "")
  const [resultado, setResultado] = useState<ResultadoCierre | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const envolver = async (f: () => Promise<unknown>) => {
    setOcupado(true)
    try {
      await f()
    } finally {
      setOcupado(false)
    }
  }

  if (resultado && !turno) {
    return (
      <div className="space-y-4">
        <Resultado r={resultado} />
        <Button type="button" onClick={() => setResultado(null)}>Entendido</Button>
      </div>
    )
  }

  if (!turno) {
    const monto = aEntero(apertura)
    return (
      <section className="max-w-md space-y-4 rounded-2xl border bg-white p-4">
        <h3 className="font-semibold">Abrir turno</h3>
        <CampoPesos etiqueta="Monto de apertura (efectivo en caja)" valor={apertura} onCambio={setApertura} />
        <Button type="button" className="h-11 w-full" disabled={ocupado || monto === null}
          onClick={() => void envolver(async () => {
            if (await escribir(abrirTurno(localId, monto as number))) {
              setApertura("")
              setDebito("")
              setCredito("")
              setNotas("")
              setConteoTexto("")
              onCambio()
            }
          })}>
          Abrir turno
        </Button>
      </section>
    )
  }

  const segundo = turno.requiere_segundo_conteo && turno.segundo_conteo === null && turno.primer_conteo !== null
  const completo = conteoCompleto(turno)
  const puedeCerrar = completo && turno.conciliacion !== null
  const montoConteo = aEntero(conteoTexto)
  const totales = [aEntero(debito), aEntero(credito), aEntero(notas)]

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border bg-white p-4 text-sm">
        <p className="font-semibold">Turno abierto</p>
        <p className="text-neutral-600">Desde {fechaHora(turno.abierto_en)} · apertura {pesos(turno.monto_apertura)}</p>
      </div>

      <Paso numero={1} titulo={segundo ? "Segundo conteo de efectivo" : "Conteo de efectivo"} hecho={completo}>
        {completo ? (
          <p className="text-sm text-neutral-600">Conteo registrado.</p>
        ) : (
          <>
            {segundo && <Aviso tipo="info">La diferencia supera lo tolerado: cuenta de nuevo el efectivo.</Aviso>}
            <p className="text-sm text-neutral-500">Cuenta el efectivo de la caja. No se muestra cuánto debería haber.</p>
            <CampoPesos etiqueta="Efectivo contado" valor={conteoTexto} onCambio={setConteoTexto} />
            <Button type="button" className="h-11" disabled={ocupado || montoConteo === null}
              onClick={() => void envolver(async () => {
                const r = await escribir<{ requiere_segundo_conteo: boolean; conteo_completado: boolean }>(
                  conteo(localId, turno.turno_id, montoConteo as number))
                if (!r) return
                setConteoTexto("")
                if (r.requiere_segundo_conteo && !r.conteo_completado) notificar("La diferencia supera lo tolerado: cuenta de nuevo el efectivo.", "info")
                onCambio()
              })}>
              Registrar conteo
            </Button>
          </>
        )}
      </Paso>

      <Paso numero={2} titulo="Conciliación del terminal" hecho={turno.conciliacion !== null}>
        <div className="grid gap-3 sm:grid-cols-3">
          <CampoPesos etiqueta="Total débito" valor={debito} onCambio={setDebito} />
          <CampoPesos etiqueta="Total crédito" valor={credito} onCambio={setCredito} />
          <CampoPesos etiqueta="Notas de crédito" valor={notas} onCambio={setNotas} />
        </div>
        <Button type="button" variant="outline" className="h-11" disabled={ocupado || totales.some((t) => t === null)}
          onClick={() => void envolver(async () => {
            if (await escribir(conciliacion(localId, turno.turno_id, {
              total_debito_pos: totales[0] as number, total_credito_pos: totales[1] as number, total_notas_credito_pos: totales[2] as number,
            }))) onCambio()
          })}>
          {turno.conciliacion ? "Corregir conciliación" : "Registrar conciliación"}
        </Button>
      </Paso>

      <Paso numero={3} titulo="Cerrar turno" hecho={false}>
        <Button type="button" className="h-11" disabled={ocupado || !puedeCerrar}
          onClick={() => void envolver(async () => {
            const r = await escribir<{ turno: Turno } & ResultadoCierre>(cerrarTurno(localId, turno.turno_id))
            if (!r) return
            setResultado(r)
            onCambio()
          })}>
          Cerrar turno
        </Button>
        {!puedeCerrar && <p className="text-xs text-neutral-500">Falta el conteo de efectivo o la conciliación del terminal.</p>}
      </Paso>
    </div>
  )
}
