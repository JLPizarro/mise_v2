import { Boxes, ChefHat, ClipboardList, LayoutDashboard, LogOut, MessagesSquare, Settings, Users, BarChart3 } from "lucide-react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { Aviso } from "@/components/comun/Aviso"
import { SelectorLocal } from "@/components/comun/SelectorLocal"
import { useEnLinea } from "@/hooks/useEnLinea"
import { NOMBRE_ROL, puede, ROLES } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

const enlace = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-11 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-medium ${isActive ? "bg-neutral-900 text-white" : "text-neutral-600 hover:bg-neutral-100"}`

/** Administración y reportes (dueño y admin). Necesita internet: sin conexión solo avisa. */
export default function AdminLayout() {
  const { yo, local, rol, salir } = useSesion()
  const navigate = useNavigate()
  const enLinea = useEnLinea()
  if (!local) return null
  const base = `/l/${local.local_id}`
  const secciones = [
    { a: `${base}/admin`, n: "Inicio", i: <LayoutDashboard className="h-4 w-4" />, fin: true },
    { a: `${base}/admin/catalogo`, n: "Catálogo", i: <ClipboardList className="h-4 w-4" /> },
    { a: `${base}/admin/salon`, n: "Salón y cocina", i: <ChefHat className="h-4 w-4" /> },
    { a: `${base}/admin/inventario`, n: "Inventario", i: <Boxes className="h-4 w-4" /> },
    { a: `${base}/admin/personal`, n: "Personal", i: <Users className="h-4 w-4" /> },
    { a: `${base}/admin/configuracion`, n: "Configuración", i: <Settings className="h-4 w-4" /> },
    { a: `${base}/admin/mensajeria`, n: "Mensajería", i: <MessagesSquare className="h-4 w-4" /> },
    { a: `${base}/admin/reportes`, n: "Reportes", i: <BarChart3 className="h-4 w-4" /> },
  ]

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="sticky top-0 z-30 border-b bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{local.nombre_local}</p>
            <p className="truncate text-xs text-neutral-500">{yo?.nombre} · {rol ? NOMBRE_ROL[rol] : ""}</p>
          </div>
          <div className="flex items-center gap-1">
            <NavLink to={`${base}/salon`} className={enlace}>Salón</NavLink>
            {puede(rol, ROLES.caja) && <NavLink to={`${base}/caja`} className={enlace}>Caja</NavLink>}
            <SelectorLocal />
            <button type="button" aria-label="Salir" title="Salir" className="rounded-lg p-2 text-neutral-500 hover:bg-neutral-100"
              onClick={() => { salir(); navigate("/ingresar", { replace: true }) }}>
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
        <nav aria-label="Administración" className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-2">
          {secciones.map((s) => (
            <NavLink key={s.a} to={s.a} end={s.fin} className={enlace}>{s.i}{s.n}</NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl space-y-4 px-4 py-6">
        {!enLinea && <Aviso tipo="error">Sin conexión: la administración necesita internet.</Aviso>}
        <Outlet />
      </main>
    </div>
  )
}
