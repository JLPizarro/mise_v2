import { useState } from "react"
import type { Medio } from "@/api/caja"
import type { MetodoPago } from "@/api/tipos"
import { CampoPesos } from "@/components/comun/CampoPesos"
import { Button } from "@/components/ui/button"
import { aEntero, pesos } from "@/lib/dinero"

const METODOS: { metodo: MetodoPago; nombre: string }[] = [
  { metodo: "efectivo", nombre: "Efectivo" },
  { metodo: "debito", nombre: "Débito" },
  { metodo: "credito", nombre: "Crédito" },
  { metodo: "transferencia", nombre: "Transferencia" },
]

interface Props {
  monto: number
  propinaInicial: number
  ocupado: boolean
  onPagar: (medios: Medio[]) => void
}

interface EstadoMedio { metodo: MetodoPago; codigo: string; recibido: string }
const medioVacio = (): EstadoMedio => ({ metodo: "efectivo", codigo: "", recibido: "" })

function SelectorMedio({ valor, onCambio, etiqueta }: { valor: EstadoMedio; onCambio: (v: EstadoMedio) => void; etiqueta: string }) {
  return (
    <div className="space-y-2">
      <label className="block space-y-1 text-sm">
        <span className="font-medium">{etiqueta}</span>
        <select value={valor.metodo} onChange={(e) => onCambio({ ...valor, metodo: e.target.value as MetodoPago })}
          className="h-11 w-full rounded-lg border bg-white px-3">
          {METODOS.map((m) => <option key={m.metodo} value={m.metodo}>{m.nombre}</option>)}
        </select>
      </label>
      {(valor.metodo === "debito" || valor.metodo === "credito") && (
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Código del terminal</span>
          <input value={valor.codigo} maxLength={64} autoComplete="off" onChange={(e) => onCambio({ ...valor, codigo: e.target.value })}
            className="h-11 w-full rounded-lg border px-3" />
        </label>
      )}
    </div>
  )
}

/**
 * 1 o 2 medios de pago. El segundo cubre lo que falta. La propina va en el primer medio. El efectivo
 * recibido debe cubrir el monto (y la propina, en el primero) de ese medio.
 */
export default function FormularioPago({ monto, propinaInicial, ocupado, onPagar }: Props) {
  const [segundo, setSegundo] = useState(false)
  const [m1, setM1] = useState<EstadoMedio>(medioVacio)
  const [m2, setM2] = useState<EstadoMedio>({ ...medioVacio(), metodo: "debito" })
  const [monto1Texto, setMonto1Texto] = useState(String(monto))
  const [propinaTexto, setPropinaTexto] = useState(String(propinaInicial))

  const propina = aEntero(propinaTexto) ?? 0
  const monto1 = segundo ? (aEntero(monto1Texto) ?? 0) : monto
  const monto2 = monto - monto1

  function errorDe(m: EstadoMedio, montoMedio: number, propinaMedio: number): string | null {
    if (m.metodo === "debito" || m.metodo === "credito") return m.codigo.trim() === "" ? "Falta el código del terminal" : null
    if (m.metodo === "efectivo") {
      const recibido = aEntero(m.recibido)
      if (recibido === null || recibido < montoMedio + propinaMedio) return "El efectivo recibido no alcanza"
    }
    return null
  }

  let error: string | null = null
  if (monto < 1) error = "No hay monto para cobrar"
  else if (segundo && (monto1 < 1 || monto2 < 1)) error = "Cada medio debe cubrir al menos $1"
  else error = errorDe(m1, monto1, propina) ?? (segundo ? errorDe(m2, monto2, 0) : null)

  const vuelto = (m: EstadoMedio, montoMedio: number, propinaMedio: number): number | null =>
    m.metodo === "efectivo" && aEntero(m.recibido) !== null ? (aEntero(m.recibido) as number) - montoMedio - propinaMedio : null

  function construir(m: EstadoMedio, montoMedio: number, propinaMedio: number): Medio {
    return {
      metodo: m.metodo, monto: montoMedio, propina: propinaMedio > 0 ? propinaMedio : undefined,
      codigo_autorizacion_pos: m.metodo === "debito" || m.metodo === "credito" ? m.codigo.trim() : undefined,
      efectivo_recibido: m.metodo === "efectivo" ? (aEntero(m.recibido) ?? 0) : undefined,
    }
  }

  const v1 = vuelto(m1, monto1, propina)
  const v2 = segundo ? vuelto(m2, monto2, 0) : null

  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault()
      if (!error) onPagar(segundo ? [construir(m1, monto1, propina), construir(m2, monto2, 0)] : [construir(m1, monto1, propina)])
    }}>
      <CampoPesos etiqueta="Propina" valor={propinaTexto} onCambio={setPropinaTexto} />

      <div className="space-y-3 rounded-xl border p-3">
        {segundo && <CampoPesos etiqueta="Monto del primer medio" valor={monto1Texto} onCambio={setMonto1Texto} />}
        <SelectorMedio etiqueta={segundo ? "Primer medio" : "Medio de pago"} valor={m1} onCambio={setM1} />
        {m1.metodo === "efectivo" && (
          <div>
            <CampoPesos etiqueta="Efectivo recibido" valor={m1.recibido} onCambio={(v) => setM1({ ...m1, recibido: v })} />
            {v1 !== null && v1 >= 0 && <p className="mt-1 text-sm text-neutral-600">Vuelto: {pesos(v1)}</p>}
          </div>
        )}
      </div>

      {segundo ? (
        <div className="space-y-3 rounded-xl border p-3">
          <p className="text-sm font-medium">Segundo medio: {pesos(Math.max(monto2, 0))}</p>
          <SelectorMedio etiqueta="Segundo medio" valor={m2} onCambio={setM2} />
          {m2.metodo === "efectivo" && (
            <div>
              <CampoPesos etiqueta="Efectivo recibido" valor={m2.recibido} onCambio={(v) => setM2({ ...m2, recibido: v })} />
              {v2 !== null && v2 >= 0 && <p className="mt-1 text-sm text-neutral-600">Vuelto: {pesos(v2)}</p>}
            </div>
          )}
          <Button type="button" variant="ghost" size="sm" onClick={() => setSegundo(false)}>Quitar segundo medio</Button>
        </div>
      ) : (
        <Button type="button" variant="outline" onClick={() => { setSegundo(true); setMonto1Texto(String(Math.max(Math.floor(monto / 2), 1))) }}>
          Pagar con dos medios
        </Button>
      )}

      {error && monto > 0 && <p className="text-sm text-neutral-500">{error}</p>}
      <Button type="submit" className="h-12 w-full text-base" disabled={ocupado || error !== null}>
        Cobrar {pesos(monto)}{propina > 0 ? ` + propina ${pesos(propina)}` : ""}
      </Button>
    </form>
  )
}
