import { LogOut } from "lucide-react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { BarraConexion } from "@/components/comun/BarraConexion"
import { useNotificar } from "@/components/comun/avisos"
import { SelectorLocal } from "@/components/comun/SelectorLocal"
import { useMesasSincronizando } from "@/hooks/useCola"
import { useEstacion } from "@/hooks/useEstacion"
import { useSondeo } from "@/hooks/useSondeo"
import { useVaciarCola } from "@/hooks/useVaciarCola"
import { sincronizacion } from "@/offline/sincronizar"
import { puede, ROLES, NOMBRE_ROL } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

const enlace = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-neutral-900 text-white" : "text-neutral-600 hover:bg-neutral-100"}`

/** Encabezado y avisos de conexión de las pantallas de operación (salón y caja). */
export default function LayoutOperacion() {
  const { yo, local, rol, salir } = useSesion()
  const notificar = useNotificar()
  const navigate = useNavigate()
  const esEstacion = useEstacion(local?.local_id) !== null
  const { enviarAhora, pendientes } = useVaciarCola(local?.local_id, esEstacion)
  const sincronizando = useMesasSincronizando()

  // Mientras haya mesas esperando al servidor, se revisa cada 3 s (5.11).
  useSondeo(() => sincronizacion.verificar((mensaje) => notificar(mensaje, "info")), 3000, sincronizando > 0)

  if (!local) return null
  const base = `/l/${local.local_id}`

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="sticky top-0 z-30 border-b bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{local.nombre_local}</p>
            <p className="truncate text-xs text-neutral-500">{yo?.nombre} · {rol ? NOMBRE_ROL[rol] : ""}</p>
          </div>
          <nav className="flex items-center gap-1">
            {puede(rol, ROLES.salon) && <NavLink to={`${base}/salon`} className={enlace}>Salón</NavLink>}
            {puede(rol, ROLES.caja) && <NavLink to={`${base}/caja`} className={enlace}>Caja</NavLink>}
            {puede(rol, ROLES.admin) && <NavLink to={`${base}/admin`} className={enlace}>Administración</NavLink>}
          </nav>
          <div className="flex items-center gap-2">
            <SelectorLocal />
            <button type="button" aria-label="Salir" title="Salir" className="rounded-lg p-2 text-neutral-500 hover:bg-neutral-100" onClick={() => {
              salir()
              navigate("/ingresar", { replace: true })
            }}>
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-7xl space-y-3 px-4 py-4">
        <BarraConexion esEstacion={esEstacion} pendientes={pendientes} enviarAhora={() => void enviarAhora()} />
        <Outlet />
      </div>
    </div>
  )
}
