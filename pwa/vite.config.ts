import { createHash } from "node:crypto"
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs"
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

/** Escribe dist/precache.json y pone la versión en dist/sw.js (cambia en cada compilación distinta). */
function precache(): Plugin {
  let salida = "dist"
  return {
    name: "pos-precache",
    apply: "build",
    configResolved(c) {
      salida = path.resolve(c.root, c.build.outDir)
    },
    closeBundle() {
      const excluir = new Set(["sw.js", "precache.json", "config.json"])
      const archivos: string[] = []
      const recorrer = (dir: string) => {
        for (const nombre of readdirSync(dir)) {
          const ruta = path.join(dir, nombre)
          if (statSync(ruta).isDirectory()) recorrer(ruta)
          else {
            const relativa = path.relative(salida, ruta).split(path.sep).join("/")
            if (!excluir.has(relativa)) archivos.push(relativa)
          }
        }
      }
      recorrer(salida)
      archivos.sort()
      const hash = createHash("sha256")
      for (const a of archivos) hash.update(a).update(readFileSync(path.join(salida, a)))
      const version = hash.digest("hex").slice(0, 12)
      writeFileSync(path.join(salida, "precache.json"), JSON.stringify({ version, archivos: archivos.map((a) => `./${a}`) }))
      const sw = path.join(salida, "sw.js")
      writeFileSync(sw, readFileSync(sw, "utf8").replaceAll("__VERSION__", version))
    },
  }
}

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss(), precache()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { port: 8000, strictPort: true },
  preview: { port: 8000, strictPort: true },
})
