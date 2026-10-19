import { leer } from "@/api/cliente"
import { crearComando, type Comando, type VistaItem } from "@/api/comandos"
import { L } from "@/api/rutas"
import type { Impresion, Item, Pedido } from "@/api/tipos"
import { ulid } from "@/lib/ulid"

export const pedido = (localId: string, pedidoId: string): Promise<Pedido> =>
  leer<Pedido>(`${L(localId)}/pedidos/${pedidoId}`)

/** P10: siempre se propone el pedido_id. Si la mesa ya tenía pedido, la respuesta trae ese. */
export const abrirPedido = (localId: string, mesaId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/pedidos`, { mesa_id: mesaId, pedido_id: ulid() }, "pedido.abrir")

export interface DatosItem { productoId: string; modificadorId?: string; observacion?: string; cantidad?: number }

/** P10: siempre se propone el item_id. `vista` solo sirve para pintar el ítem antes de la respuesta. */
export const agregarItem = (localId: string, pedidoId: string, mesaId: string, d: DatosItem, vista: VistaItem): Comando =>
  crearComando(localId, "POST", `${L(localId)}/pedidos/${pedidoId}/items`, {
    pedido_id: pedidoId, mesa_id: mesaId, item_id: ulid(), producto_id: d.productoId,
    cantidad: d.cantidad ?? 1, modificador_id: d.modificadorId, observacion: d.observacion,
  }, "pedido.agregar_item", vista)

/** `observacion: ""` borra la observación. */
export const modificarItem = (
  localId: string, pedidoId: string, mesaId: string, itemId: string, cambios: { cantidad?: number; observacion?: string },
): Comando =>
  crearComando(localId, "PATCH", `${L(localId)}/pedidos/${pedidoId}/items/${itemId}`, {
    pedido_id: pedidoId, item_id: itemId, mesa_id: mesaId, cantidad: cambios.cantidad, observacion: cambios.observacion,
  }, "pedido.modificar_item")

export const quitarItem = (localId: string, pedidoId: string, mesaId: string, itemId: string): Comando =>
  crearComando(localId, "DELETE", `${L(localId)}/pedidos/${pedidoId}/items/${itemId}`, {
    pedido_id: pedidoId, item_id: itemId, mesa_id: mesaId,
  }, "pedido.quitar_item")

export const enviarTanda = (localId: string, pedidoId: string, mesaId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/pedidos/${pedidoId}/enviar`, { pedido_id: pedidoId, mesa_id: mesaId }, "pedido.enviar_tanda")

export const precuenta = (localId: string, pedidoId: string, mesaId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/pedidos/${pedidoId}/precuenta`, { pedido_id: pedidoId, mesa_id: mesaId }, "pedido.precuenta")

export const reabrir = (localId: string, pedidoId: string, mesaId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/pedidos/${pedidoId}/reabrir`, {
    pedido_id: pedidoId, mesa_id: mesaId, confirmado: true,
  }, "pedido.reabrir")

export interface RespuestaEnviar { tanda: number | null; items: Item[]; impresion: Impresion[] }
export interface RespuestaPrecuenta { pedido: Pedido; items_en_espera: number }
