/** Mismas reglas que pos_dominio/mensajeria.validar_destino: avisar antes de enviar. El servidor decide. */

const NOMBRE = /^[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ][0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ _-]{0,59}$/
const CORREO = /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/

export interface ErroresDestino { nombre?: string; correo?: string; avisos?: string }

export function validarDestino(d: { nombre: string; tipo: "correo" | "cola"; correo: string; avisos: string[] }): ErroresDestino {
  const errores: ErroresDestino = {}
  if (!NOMBRE.test(d.nombre.trim())) errores.nombre = "De 1 a 60 letras, números, espacios, guiones o _"
  if (d.tipo === "correo" && (d.correo.trim().length > 254 || !CORREO.test(d.correo.trim()))) errores.correo = "Indica un correo válido"
  if (d.avisos.length === 0) errores.avisos = "Elige al menos un aviso (una regla de distribución)"
  return errores
}
