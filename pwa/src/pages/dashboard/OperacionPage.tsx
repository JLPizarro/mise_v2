import CuartosImpresoras from "@/components/dashboard/CuartosImpresoras"
import SectoresMesas from "@/components/dashboard/SectoresMesas"
import { useSesion } from "@/sesion/useSesion"

export default function OperacionPage() {
  const { local } = useSesion()
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Salón y cocina</h1>
      <div className="grid gap-6 xl:grid-cols-2">
        <SectoresMesas localId={local!.local_id} />
        <CuartosImpresoras localId={local!.local_id} />
      </div>
    </div>
  )
}
