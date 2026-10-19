import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import App from "./App"
import { cargarConfig } from "./config"

const raiz = createRoot(document.getElementById("root")!)

cargarConfig().then(
  () => {
    raiz.render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
  },
  () => {
    raiz.render(
      <main className="flex min-h-screen items-center justify-center p-4 text-center text-sm text-red-700">
        No se pudo cargar la configuración (config.json).
      </main>,
    )
  },
)
