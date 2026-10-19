import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useSesion } from "@/sesion/useSesion"

export default function SinAcceso() {
  const { errorAcceso, salir } = useSesion()
  const navigate = useNavigate()
  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 p-4">
      <section className="w-full max-w-md space-y-4 rounded-3xl border bg-white p-8 text-center shadow-xl">
        <h1 className="text-xl font-semibold">Sin acceso</h1>
        <p className="text-sm text-neutral-600">{errorAcceso?.mensaje ?? "Tu cuenta no tiene acceso a MISE."}</p>
        <Button
          type="button"
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
