import { Navigate } from "react-router-dom"
import { inicioDelRol } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

/** `/l/:localId` sin sección: va al inicio del rol en ese local. */
export default function InicioDelLocal() {
  const { local, rol } = useSesion()
  if (!local || !rol) return <Navigate to="/" replace />
  return <Navigate to={inicioDelRol(rol, local.local_id) ?? "/sin-pantalla"} replace />
}
