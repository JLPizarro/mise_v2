import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { registrarServiceWorker } from "@/pwa/registrarServiceWorker"

/** Registra el service worker y, cuando hay una versión nueva ya descargada, ofrece actualizar. */
export default function VersionNueva() {
  const [aplicar, setAplicar] = useState<(() => void) | null>(null)

  useEffect(() => {
    registrarServiceWorker((fn) => setAplicar(() => fn))
  }, [])

  if (!aplicar) return null
  return (
    <div role="status" className="fixed inset-x-0 top-0 z-[60] flex items-center justify-center gap-3 bg-neutral-900 px-4 py-2 text-sm text-white">
      <span>Hay una versión nueva</span>
      <span aria-hidden>·</span>
      <Button type="button" size="sm" variant="secondary" onClick={aplicar}>Actualizar</Button>
    </div>
  )
}
