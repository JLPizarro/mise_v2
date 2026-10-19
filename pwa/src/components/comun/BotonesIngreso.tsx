import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { config } from "@/config"
import { estacionActiva } from "@/offline/estacion"
import { cargarGoogle, dibujarBotonGoogle, ingresarDev, intentarIngresoSilencioso } from "@/sesion/google"
import { localGuardado } from "@/sesion/localGuardado"

const PERSONAS_DE_PRUEBA = ["mock-dueno", "mock-admin", "mock-cajero", "mock-garzon", "mock-garzon2", "mock-cocina"]

/** Botón de Google o, con `modo_dev`, los botones «Entrar como mock-…». */
export function BotonesIngreso() {
  const { modo_dev, google_client_id } = config()
  const contenedor = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (modo_dev || !google_client_id) return
    const local = localGuardado()
    const autoSeleccion = local === null || estacionActiva(local) === null
    let vigente = true
    cargarGoogle(autoSeleccion).then(
      () => {
        if (!vigente) return
        if (contenedor.current) dibujarBotonGoogle(contenedor.current)
        intentarIngresoSilencioso()
      },
      (e: unknown) => vigente && setError(e instanceof Error ? e.message : "No se pudo cargar el inicio de sesión"),
    )
    return () => {
      vigente = false
    }
  }, [modo_dev, google_client_id])

  if (modo_dev) {
    return (
      <div className="space-y-2">
        <p className="text-center text-xs text-amber-700">Modo de desarrollo: no funciona en la nube.</p>
        {PERSONAS_DE_PRUEBA.map((sub) => (
          <Button key={sub} type="button" variant="outline" className="h-11 w-full" onClick={() => ingresarDev(sub)}>
            Entrar como {sub}
          </Button>
        ))}
      </div>
    )
  }
  if (!google_client_id) {
    return <p className="text-center text-sm text-red-700">Falta configurar el ID de cliente de Google (config.json).</p>
  }
  return (
    <div className="space-y-2">
      <div ref={contenedor} className="flex min-h-11 justify-center" />
      {error && <p className="text-center text-sm text-red-700">{error}</p>}
    </div>
  )
}
