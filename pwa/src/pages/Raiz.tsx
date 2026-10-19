import { Outlet } from "react-router-dom"
import { Notificaciones } from "@/components/comun/Notificaciones"
import { SesionProvider } from "@/sesion/SesionProvider"

/** Raíz de todas las rutas: avisos y sesión (la sesión lee el local de la URL). */
export default function Raiz() {
  return (
    <Notificaciones>
      <SesionProvider>
        <Outlet />
      </SesionProvider>
    </Notificaciones>
  )
}
