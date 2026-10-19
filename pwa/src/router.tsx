import { createHashRouter, Navigate, Outlet } from "react-router-dom"
import AdminLayout from "@/layouts/AdminLayout"
import LayoutOperacion from "@/layouts/LayoutOperacion"
import LoginPage from "@/pages/auth/LoginPage"
import PanelCaja from "@/pages/caja/PanelCaja"
import CatalogoPage from "@/pages/dashboard/CatalogoPage"
import ConfiguracionPage from "@/pages/dashboard/ConfiguracionPage"
import DashboardPage from "@/pages/dashboard/DashboardPage"
import InventarioPage from "@/pages/dashboard/InventarioPage"
import MensajeriaPage from "@/pages/dashboard/MensajeriaPage"
import OperacionPage from "@/pages/dashboard/OperacionPage"
import ReportesPage from "@/pages/dashboard/ReportesPage"
import ReporteTurnoPage from "@/pages/dashboard/ReporteTurnoPage"
import UsuariosPage from "@/pages/dashboard/UsuariosPage"
import SinAcceso from "@/pages/auth/SinAcceso"
import SinPantalla from "@/pages/auth/SinPantalla"
import Inicio from "@/pages/Inicio"
import InicioDelLocal from "@/pages/InicioDelLocal"
import Raiz from "@/pages/Raiz"
import SelectorLocalPage from "@/pages/locales/SelectorLocalPage"
import OrderPage from "@/pages/pos/OrderPage"
import TablesPage from "@/pages/pos/TablesPage"
import { RequiereLocal } from "@/sesion/RequiereLocal"
import { RequiereRol, RequiereSesion } from "@/sesion/RequiereRol"
import { ROLES } from "@/sesion/roles"

const protegida = (elemento: React.ReactNode) => <RequiereSesion>{elemento}</RequiereSesion>

export const router = createHashRouter([
  {
    element: <Raiz />,
    children: [
      { path: "/ingresar", element: <LoginPage /> },
      { path: "/sin-acceso", element: <SinAcceso /> },
      { path: "/sin-pantalla", element: protegida(<SinPantalla />) },
      { path: "/locales", element: protegida(<SelectorLocalPage />) },
      { path: "/", element: protegida(<Inicio />) },
      {
        path: "/l/:localId",
        element: protegida(<RequiereLocal><Outlet /></RequiereLocal>),
        children: [
          { index: true, element: <InicioDelLocal /> },
          {
            element: <LayoutOperacion />,
            children: [
              { path: "salon", element: <RequiereRol roles={ROLES.salon}><TablesPage /></RequiereRol> },
              { path: "salon/mesas/:mesaId", element: <RequiereRol roles={ROLES.salon}><OrderPage /></RequiereRol> },
              { path: "caja", element: <RequiereRol roles={ROLES.caja}><PanelCaja /></RequiereRol> },
            ],
          },
          {
            path: "admin",
            element: <RequiereRol roles={ROLES.admin}><AdminLayout /></RequiereRol>,
            children: [
              { index: true, element: <DashboardPage /> },
              { path: "catalogo", element: <CatalogoPage /> },
              { path: "salon", element: <OperacionPage /> },
              { path: "cocina", element: <OperacionPage /> },
              { path: "inventario", element: <InventarioPage /> },
              { path: "personal", element: <UsuariosPage /> },
              { path: "configuracion", element: <ConfiguracionPage /> },
              { path: "mensajeria", element: <MensajeriaPage /> },
              { path: "reportes", element: <ReportesPage /> },
              { path: "reportes/turnos/:turnoId", element: <ReporteTurnoPage /> },
            ],
          },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
])
