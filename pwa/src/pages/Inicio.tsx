import { Navigate } from "react-router-dom"
import { guardarLocal, localGuardado } from "@/sesion/localGuardado"
import { inicioDelRol } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

/** `/` lleva al inicio del rol (3.4). Con más de un local y ninguno elegido: /locales. */
export default function Inicio() {
  const { yo } = useSesion()
  if (!yo || yo.locales.length === 0) return <Navigate to="/sin-acceso" replace />

  const elegido = yo.locales.find((l) => l.local_id === localGuardado()) ?? (yo.locales.length === 1 ? yo.locales[0] : null)
  if (!elegido) return <Navigate to="/locales" replace />
  guardarLocal(elegido.local_id)
  return <Navigate to={inicioDelRol(elegido.rol, elegido.local_id) ?? "/sin-pantalla"} replace />
}
