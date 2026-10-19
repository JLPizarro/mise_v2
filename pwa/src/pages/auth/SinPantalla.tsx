import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useSesion } from "@/sesion/useSesion"

export default function SinPantalla() {
  const { salir } = useSesion()
  const navigate = useNavigate()
  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 p-4">
      <section className="w-full max-w-md space-y-4 rounded-3xl border bg-white p-8 text-center shadow-xl">
        <h1 className="text-xl font-semibold">Tu rol no tiene pantalla en la PWA</h1>
        <p className="text-sm text-neutral-600">Usa el equipo de la cocina o pide a un administrador que revise tu rol.</p>
        <Button
          type="button"
          variant="outline"
          className="h-11 w-full"
          onClick={() => {
            salir()
            navigate("/ingresar", { replace: true })
          }}
        >
          Usar otra cuenta
        </Button>
      </section>
    </main>
  )
}
