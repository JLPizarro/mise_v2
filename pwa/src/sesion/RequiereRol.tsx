import type { ReactNode } from "react"
import { Navigate, useLocation } from "react-router-dom"
import { Button } from "@/components/ui/button"
import type { Rol } from "@/api/tipos"
import { inicioDelRol } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

function Cargando() {
  return <div className="flex min-h-screen items-center justify-center text-sm text-neutral-500">Cargando…</div>
}

/** Exige sesión (o sesión guardada de la estación sin conexión). Sin ella, lleva a /ingresar. */
export function RequiereSesion({ children }: { children: ReactNode }) {
  const { sesion, yo, cargando, errorAcceso, errorCarga, cerrada, reintentar, salir } = useSesion()
  const ubicacion = useLocation()

  if (errorAcceso) return <Navigate to="/sin-acceso" replace />
  if (yo) return <>{children}</>
  if (errorCarga) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-4 text-center">
        <p className="text-sm text-neutral-700">{errorCarga}</p>
        <div className="flex gap-2">
          <Button type="button" onClick={reintentar}>Reintentar</Button>
          <Button type="button" variant="outline" onClick={salir}>Usar otra cuenta</Button>
        </div>
      </div>
    )
  }
  if (sesion.token || cargando) return <Cargando />
  return <Navigate to="/ingresar" replace state={{ desde: cerrada ? undefined : ubicacion.pathname }} />
}

/** Exige uno de los roles en el local de la URL; si no corresponde, lleva al inicio del rol. */
export function RequiereRol({ roles, children }: { roles: readonly Rol[]; children: ReactNode }) {
  const { local, rol } = useSesion()
  if (!local || !rol) return <Navigate to="/" replace />
  if (!roles.includes(rol)) return <Navigate to={inicioDelRol(rol, local.local_id) ?? "/sin-pantalla"} replace />
  return <>{children}</>
}
