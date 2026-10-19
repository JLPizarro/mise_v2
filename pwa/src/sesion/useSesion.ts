import { useContext } from "react"
import { SesionContexto, type ValorSesion } from "@/sesion/contexto"

export function useSesion(): ValorSesion {
  const valor = useContext(SesionContexto)
  if (!valor) throw new Error("useSesion se usa dentro de SesionProvider")
  return valor
}
