export function registrarServiceWorker(alHaberVersionNueva: (aplicar: () => void) => void): void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return
  const habiaControlador = navigator.serviceWorker.controller !== null
  let recargando = false
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (habiaControlador && !recargando) {
      recargando = true
      window.location.reload()
    }
  })
  void navigator.serviceWorker.register("./sw.js").then((registro) => {
    const avisar = (sw: ServiceWorker) => alHaberVersionNueva(() => sw.postMessage({ tipo: "ACTUALIZAR" }))
    if (registro.waiting && navigator.serviceWorker.controller) avisar(registro.waiting)
    registro.addEventListener("updatefound", () => {
      const nuevo = registro.installing
      nuevo?.addEventListener("statechange", () => {
        if (nuevo.state === "installed" && navigator.serviceWorker.controller) avisar(nuevo)
      })
    })
    window.setInterval(() => void registro.update(), 30 * 60_000)
  })
}
