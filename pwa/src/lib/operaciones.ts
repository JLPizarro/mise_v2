/** Nombre en palabras de las operaciones de comanda (bandeja de conflictos, cola local). */
export const NOMBRE_OPERACION: Record<string, string> = {
  "pedido.abrir": "Abrir mesa",
  "pedido.agregar_item": "Agregar ítem",
  "pedido.modificar_item": "Modificar ítem",
  "pedido.quitar_item": "Quitar ítem",
  "pedido.enviar_tanda": "Enviar a cocina",
  "pedido.precuenta": "Precuenta",
  "pedido.reabrir": "Reabrir mesa",
}

export const nombreOperacion = (operacion: string): string => NOMBRE_OPERACION[operacion] ?? operacion
