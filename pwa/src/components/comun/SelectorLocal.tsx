import { useLocation, useNavigate } from "react-router-dom"
import { guardarLocal } from "@/sesion/localGuardado"
import { inicioDelRol } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

/** Cambia de local cuando la persona tiene más de uno (P7). Nada si hay uno solo. */
export function SelectorLocal() {
  const { yo, local } = useSesion()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  if (!yo || yo.locales.length < 2 || !local) return null

  return (
    <select
      aria-label="Local"
      className="h-9 rounded-lg border bg-white px-2 text-sm"
      value={local.local_id}
      onChange={(e) => {
        const nuevo = yo.locales.find((l) => l.local_id === e.target.value)
        if (!nuevo) return
        guardarLocal(nuevo.local_id)
        // Misma sección en el otro local si el rol la permite; si no, el inicio de su rol.
        const seccion = pathname.split("/").slice(3, 4)[0]
        const mismo = seccion ? `/l/${nuevo.local_id}/${seccion}` : null
        const inicio = inicioDelRol(nuevo.rol, nuevo.local_id)
        navigate(mismo && inicio?.endsWith(`/${seccion}`) ? mismo : (inicio ?? "/sin-pantalla"))
      }}
    >
      {yo.locales.map((l) => (
        <option key={l.local_id} value={l.local_id}>{l.nombre_local}</option>
      ))}
    </select>
  )
}
