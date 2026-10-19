import { useNavigate } from "react-router-dom"
import { guardarLocal } from "@/sesion/localGuardado"
import { inicioDelRol, NOMBRE_ROL } from "@/sesion/roles"
import { useSesion } from "@/sesion/useSesion"

export default function SelectorLocalPage() {
  const { yo, salir } = useSesion()
  const navigate = useNavigate()

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 p-4">
      <section className="w-full max-w-md space-y-4 rounded-3xl border bg-white p-8 shadow-xl">
        <div className="text-center">
          <h1 className="text-xl font-semibold">Elige un local</h1>
          <p className="mt-1 text-sm text-neutral-600">{yo?.nombre}</p>
        </div>
        <ul className="space-y-2">
          {yo?.locales.map((l) => (
            <li key={l.local_id}>
              <button
                type="button"
                className="flex min-h-14 w-full items-center justify-between rounded-xl border px-4 text-left hover:bg-neutral-50"
                onClick={() => {
                  guardarLocal(l.local_id)
                  navigate(inicioDelRol(l.rol, l.local_id) ?? "/sin-pantalla")
                }}
              >
                <span>
                  <span className="block font-medium">{l.nombre_local}</span>
                  <span className="block text-xs text-neutral-500">{l.marca}</span>
                </span>
                <span className="text-xs text-neutral-600">{NOMBRE_ROL[l.rol]}</span>
              </button>
            </li>
          ))}
        </ul>
        <button type="button" className="w-full text-center text-sm text-neutral-500 underline" onClick={salir}>
          Usar otra cuenta
        </button>
      </section>
    </main>
  )
}
