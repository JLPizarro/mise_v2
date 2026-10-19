import { ErrorApi } from "@/api/cliente"
import type { Comando } from "@/api/comandos"
import type { Item, MesaPlano, Pedido } from "@/api/tipos"
import { estadoSesion } from "@/sesion/google"

/**
 * Reproduce las reglas de operaciones/pedidos.py para mostrar el efecto de comandos todavía no
 * confirmados. "validar" lanza con los mismos códigos y mensajes del servidor; "superponer" nunca lanza.
 */
export type ModoAplicar = "validar" | "superponer"

class Rechazo extends Error {
  readonly http: number
  readonly codigo: string
  constructor(http: number, codigo: string, mensaje: string) {
    super(mensaje)
    this.http = http
    this.codigo = codigo
  }
}
const noEncontrado = (codigo: string, mensaje: string) => new Rechazo(404, codigo, mensaje)
const conflicto = (codigo: string, mensaje: string) => new Rechazo(409, codigo, mensaje)
const invalido = (codigo: string, mensaje: string) => new Rechazo(422, codigo, mensaje)

const MSG_PRECUENTA = "La mesa está en precuenta. Reábrela para modificar la comanda."

function recalcular(p: Pedido): Pedido {
  const total = p.items.reduce((suma, i) => suma + i.subtotal, 0)
  return { ...p, total, saldo: total - p.pagado }
}

function exigirPedido(p: Pedido | null): Pedido {
  if (p === null) throw noEncontrado("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado")
  return p
}

function exigirAbierto(p: Pedido): void {
  if (p.estado === "precuenta") throw conflicto("PEDIDO_EN_PRECUENTA", MSG_PRECUENTA)
  if (p.estado === "cerrado") throw conflicto("PEDIDO_CERRADO", "El pedido ya está cerrado")
}

function exigirItem(p: Pedido, itemId: string): Item {
  const item = p.items.find((i) => i.item_id === itemId)
  if (!item) throw noEncontrado("ITEM_NO_ENCONTRADO", "Item no encontrado")
  return item
}

function exigirEnEspera(i: Item): void {
  if (i.estado !== "en_espera") {
    throw conflicto("ITEM_YA_ENVIADO", "El ítem ya fue enviado a cocina y no se puede modificar")
  }
}

const texto = (valor: unknown): string | null => (typeof valor === "string" && valor !== "" ? valor : null)

function pedidoNuevo(c: Comando): Pedido {
  return {
    pedido_id: String(c.cuerpo.pedido_id), mesa_id: String(c.cuerpo.mesa_id), estado: "abierto",
    items: [], pagos: [], total: 0, pagado: 0, saldo: 0, propina_total: 0, n_tandas: 0,
    garzon_id: estadoSesion().sub, documento: null, creado_en: c.creadoEn, cerrado_en: null,
  }
}

function calcular(pedido: Pedido | null, c: Comando): Pedido | null {
  const cuerpo = c.cuerpo
  switch (c.operacion) {
    case "pedido.abrir":
      return pedido !== null && pedido.estado !== "cerrado" ? pedido : pedidoNuevo(c)

    case "pedido.agregar_item": {
      const p = exigirPedido(pedido)
      exigirAbierto(p)
      const itemId = String(cuerpo.item_id)
      if (p.items.some((i) => i.item_id === itemId) || !c.vistaItem) return p
      const cantidad = Number(cuerpo.cantidad ?? 1)
      const v = c.vistaItem
      const item: Item = {
        item_id: itemId, producto_id: String(cuerpo.producto_id), nombre: v.nombre, categoria: v.categoria,
        cuarto_id: v.cuarto_id, modificador_id: texto(cuerpo.modificador_id), modificador_nombre: v.modificador_nombre,
        cantidad, cobrado: 0, precio_unitario: v.precio_unitario, subtotal: v.precio_unitario * cantidad,
        estado: "en_espera", tanda: null, observacion: texto(cuerpo.observacion), creado_en: c.creadoEn, enviado_en: null,
      }
      return { ...p, items: [...p.items, item] }
    }

    case "pedido.modificar_item": {
      const p = exigirPedido(pedido)
      exigirAbierto(p)
      const itemActual = exigirItem(p, String(cuerpo.item_id))
      exigirEnEspera(itemActual)
      const cantidad = typeof cuerpo.cantidad === "number" ? cuerpo.cantidad : itemActual.cantidad
      const observacion = "observacion" in cuerpo ? texto(cuerpo.observacion) : itemActual.observacion
      const nuevo: Item = { ...itemActual, cantidad, observacion, subtotal: itemActual.precio_unitario * cantidad }
      return { ...p, items: p.items.map((i) => (i.item_id === nuevo.item_id ? nuevo : i)) }
    }

    case "pedido.quitar_item": {
      const p = exigirPedido(pedido)
      exigirAbierto(p)
      const itemId = String(cuerpo.item_id)
      const existente = p.items.find((i) => i.item_id === itemId)
      if (!existente) return p
      exigirEnEspera(existente)
      return { ...p, items: p.items.filter((i) => i.item_id !== itemId) }
    }

    case "pedido.enviar_tanda": {
      const p = exigirPedido(pedido)
      exigirAbierto(p)
      if (!p.items.some((i) => i.estado === "en_espera")) return p
      const tanda = p.n_tandas + 1
      const items = p.items.map((i): Item =>
        i.estado === "en_espera" ? { ...i, estado: "enviado", tanda, enviado_en: c.creadoEn } : i)
      return { ...p, items, n_tandas: tanda }
    }

    case "pedido.precuenta": {
      const p = exigirPedido(pedido)
      if (p.estado === "precuenta") return p
      if (p.estado === "cerrado") throw conflicto("PEDIDO_CERRADO", "El pedido ya está cerrado")
      if (p.items.length === 0) throw invalido("PEDIDO_VACIO", "La mesa no tiene consumo")
      return { ...p, estado: "precuenta" }
    }

    case "pedido.reabrir": {
      const p = exigirPedido(pedido)
      if (p.estado === "abierto") return p
      if (p.estado === "cerrado") throw conflicto("PEDIDO_CERRADO", "El pedido ya está cerrado")
      if (cuerpo.confirmado !== true) {
        throw invalido("CONFIRMACION_REQUERIDA", "Reabrir la mesa deja sin efecto la precuenta. Confirma para continuar.")
      }
      return { ...p, estado: "abierto" }
    }

    default:
      return pedido
  }
}

export function aplicar(pedido: Pedido | null, c: Comando, modo: ModoAplicar): Pedido | null {
  try {
    const resultado = calcular(pedido, c)
    return resultado === null ? null : recalcular(resultado)
  } catch (e) {
    if (modo === "validar" && e instanceof Rechazo) throw new ErrorApi(e.http, e.codigo, e.message)
    if (e instanceof Rechazo) return pedido
    throw e
  }
}

const porId = (a: Item, b: Item) => (a.item_id < b.item_id ? -1 : a.item_id > b.item_id ? 1 : 0)

export function huella(p: Pedido | null): string {
  return p === null
    ? "null"
    : JSON.stringify([p.estado, [...p.items].sort(porId).map((i) => [i.item_id, i.cantidad, i.observacion ?? null, i.estado])])
}

export function estadoMesa(mesa: MesaPlano, comandos: Comando[]): MesaPlano {
  let resultado = mesa
  for (const c of comandos) {
    if (c.operacion === "pedido.abrir") {
      resultado = { ...resultado, estado: "ocupada", pedido_id: String(c.cuerpo.pedido_id) }
    } else if (c.operacion === "pedido.precuenta") {
      resultado = { ...resultado, estado: "precuenta" }
    } else if (c.operacion === "pedido.reabrir") {
      resultado = { ...resultado, estado: "ocupada" }
    }
  }
  return resultado
}
