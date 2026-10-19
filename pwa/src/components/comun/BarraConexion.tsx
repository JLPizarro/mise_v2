import { useState } from "react"
import { Aviso } from "@/components/comun/Aviso"
import { BotonesIngreso } from "@/components/comun/BotonesIngreso"
import { Button } from "@/components/ui/button"
import { useMesasSincronizando } from "@/hooks/useCola"
import { useEnLinea } from "@/hooks/useEnLinea"
import { useSesion } from "@/sesion/useSesion"

interface Props {
  esEstacion: boolean
  pendientes: number
  enviarAhora: () => void
}

const plural = (n: number, uno: string, varios: string) => (n === 1 ? `1 ${uno}` : `${n} ${varios}`)

export function BarraConexion({ esEstacion, pendientes, enviarAhora }: Props) {
  const enLinea = useEnLinea()
  const { vencida, sinConexionSoloLectura } = useSesion()
  const sincronizando = useMesasSincronizando()
  const [ingresando, setIngresando] = useState(false)

  return (
    <div className="space-y-2">
      {sinConexionSoloLectura && (
        <Aviso tipo="info">
          Sin conexión. Ingresa cuando vuelva internet para enviar {plural(pendientes, "comanda", "comandas")}.
        </Aviso>
      )}

      {!sinConexionSoloLectura && !enLinea && (
        <Aviso tipo="error">
          {esEstacion
            ? `Sin conexión: las comandas se guardan en este equipo (${plural(pendientes, "pendiente", "pendientes")})`
            : "Sin conexión: usa la caja"}
        </Aviso>
      )}

      {vencida && (
        <Aviso tipo="info">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {pendientes > 0
                ? `Ingresa para enviar ${plural(pendientes, "comanda guardada", "comandas guardadas")}`
                : "Tu sesión venció. Ingresa para continuar."}
            </span>
            <Button type="button" size="sm" onClick={() => setIngresando((v) => !v)}>Ingresar</Button>
          </div>
          {ingresando && <div className="mt-3"><BotonesIngreso /></div>}
        </Aviso>
      )}

      {sincronizando > 0 && (
        <Aviso tipo="info">Sincronizando {plural(sincronizando, "mesa", "mesas")}…</Aviso>
      )}

      {esEstacion && enLinea && !vencida && pendientes > 0 && (
        <Aviso tipo="info">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>{plural(pendientes, "comanda guardada", "comandas guardadas")} en este equipo.</span>
            <Button type="button" size="sm" onClick={enviarAhora}>Enviar ahora</Button>
          </div>
        </Aviso>
      )}
    </div>
  )
}
