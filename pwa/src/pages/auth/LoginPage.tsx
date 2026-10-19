import { useEffect } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import miseLogo from "@/assets/branding/mise-logo-slogan.png"
import { BotonesIngreso } from "@/components/comun/BotonesIngreso"
import { useSesion } from "@/sesion/useSesion"

export default function LoginPage() {
  const { sesion, sinConexionSoloLectura } = useSesion()
  const navigate = useNavigate()
  const destino = (useLocation().state as { desde?: string } | null)?.desde ?? "/"

  useEffect(() => {
    // También con la estación sin conexión: sigue con la última sesión guardada (P17).
    if (sesion.token || sinConexionSoloLectura) navigate(destino, { replace: true })
  }, [sesion.token, sinConexionSoloLectura, destino, navigate])

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 p-4">
      <section className="w-full max-w-md rounded-3xl border bg-white p-8 shadow-xl sm:p-10">
        <div className="mb-8 flex justify-center">
          <img src={miseLogo} alt="MISE - Todo en su lugar" className="w-64 sm:w-72" />
        </div>
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-950">Bienvenido a MISE</h1>
          <p className="mt-3 text-sm leading-6 text-neutral-600">Gestiona tu restaurante desde un solo lugar.</p>
        </div>
        <BotonesIngreso />
        <div className="mt-10 border-t pt-6 text-center">
          <p className="text-xs leading-5 text-neutral-500">Acceso exclusivo para personal autorizado.</p>
          <p className="mt-2 text-xs text-neutral-400">MISE · Sistema de gestión para restaurantes</p>
        </div>
      </section>
    </main>
  )
}
