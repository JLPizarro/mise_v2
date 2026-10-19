/* Service worker de la PWA. La compilación escribe aquí la versión (ver vite.config.ts). */
const VERSION = "__VERSION__"
const CACHE = `pos-${VERSION}`

self.addEventListener("install", (evento) => {
  evento.waitUntil((async () => {
    const respuesta = await fetch("./precache.json", { cache: "no-store" })
    const { archivos } = await respuesta.json()
    const cache = await caches.open(CACHE)
    await cache.addAll(archivos)
  })())
})

self.addEventListener("activate", (evento) => {
  evento.waitUntil((async () => {
    for (const nombre of await caches.keys()) {
      if (nombre.startsWith("pos-") && nombre !== CACHE) await caches.delete(nombre)
    }
    await self.clients.claim()
  })())
})

self.addEventListener("message", (evento) => {
  if (evento.data && evento.data.tipo === "ACTUALIZAR") self.skipWaiting()
})

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request
  const url = new URL(peticion.url)
  if (peticion.method !== "GET" || url.origin !== self.location.origin) return // la API nunca pasa por aquí
  const archivo = url.pathname.split("/").pop() || ""
  if (peticion.mode === "navigate" || archivo === "index.html") {
    evento.respondWith(redPrimero(peticion, "./index.html"))
  } else if (archivo === "config.json") {
    evento.respondWith(redPrimero(peticion, null))
  } else {
    evento.respondWith(cachePrimero(peticion))
  }
})

async function redPrimero(peticion, respaldo) {
  const cache = await caches.open(CACHE)
  try {
    const respuesta = await fetch(peticion, { cache: "no-store" })
    if (respuesta.ok) await cache.put(peticion, respuesta.clone())
    return respuesta
  } catch {
    const guardada = await cache.match(peticion, { ignoreSearch: true })
    if (guardada) return guardada
    if (respaldo) {
      const indice = await cache.match(respaldo)
      if (indice) return indice
    }
    return Response.error()
  }
}

async function cachePrimero(peticion) {
  const guardada = await caches.match(peticion, { ignoreSearch: true })
  if (guardada) return guardada
  const respuesta = await fetch(peticion)
  if (respuesta.ok) {
    const cache = await caches.open(CACHE)
    await cache.put(peticion, respuesta.clone())
  }
  return respuesta
}
