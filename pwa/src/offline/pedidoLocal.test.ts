import { beforeEach, describe, expect, it } from "vitest"
import { ErrorApi } from "@/api/cliente"
import { crearComando, type Comando, type OperacionComanda } from "@/api/comandos"
import type { Item, MesaPlano, Pedido } from "@/api/tipos"
import { aplicar, estadoMesa, huella } from "@/offline/pedidoLocal"
import { prepararEntorno } from "@/test/ayudas"

const L = "local_01"
const cmd = (operacion: OperacionComanda, cuerpo: Record<string, unknown>, vista?: Comando["vistaItem"]) =>
  crearComando(L, "POST", "/x", { mesa_id: "m03", pedido_id: "P1", ...cuerpo }, operacion, vista)

const VISTA = { nombre: "Pizza", categoria: "Fondos" as const, cuarto_id: "cu", precio_unitario: 5000, modificador_nombre: null }
const abrir = () => cmd("pedido.abrir", {})
const agregar = (id = "I1", cantidad = 2) => cmd("pedido.agregar_item", { item_id: id, producto_id: "pr", cantidad }, VISTA)

function pedidoCon(estado: Pedido["estado"], items: Item[] = []): Pedido {
  return {
    pedido_id: "P1", mesa_id: "m03", garzon_id: "g", estado, total: 0, pagado: 0, saldo: 0, propina_total: 0, n_tandas: 0,
    documento: null, creado_en: "", cerrado_en: null, items, pagos: [],
  }
}
const itemEn = (estado: Item["estado"], id = "I1"): Item => ({
  item_id: id, producto_id: "pr", nombre: "Pizza", categoria: "Fondos", cuarto_id: "cu", modificador_id: null,
  modificador_nombre: null, cantidad: 2, cobrado: 0, precio_unitario: 5000, subtotal: 10000, estado,
  tanda: estado === "enviado" ? 1 : null, observacion: null, creado_en: "", enviado_en: null,
})

function falla(p: Pedido | null, c: Comando): ErrorApi {
  try {
    aplicar(p, c, "validar")
  } catch (e) {
    return e as ErrorApi
  }
  throw new Error("Debía lanzar")
}

beforeEach(() => prepararEntorno("mock-garzon"))

describe("pedido.abrir", () => {
  it("crea un pedido nuevo con el ID propuesto", () => {
    const p = aplicar(null, abrir(), "validar")!
    expect([p.pedido_id, p.mesa_id, p.estado, p.garzon_id, p.items.length]).toEqual(["P1", "m03", "abierto", "mock-garzon", 0])
  })
  it("si ya hay uno no cerrado, no cambia", () => {
    const existente = pedidoCon("precuenta")
    expect(aplicar(existente, abrir(), "validar")).toEqual(existente)
  })
})

describe("pedido.agregar_item", () => {
  it("agrega el ítem y recalcula el total", () => {
    const p = aplicar(pedidoCon("abierto"), agregar(), "validar")!
    expect(p.items).toHaveLength(1)
    expect([p.items[0].subtotal, p.items[0].estado, p.total, p.saldo]).toEqual([10000, "en_espera", 10000, 10000])
  })
  it("sin pedido: PEDIDO_NO_ENCONTRADO", () => {
    const e = falla(null, agregar())
    expect([e.http, e.codigo, e.message]).toEqual([404, "PEDIDO_NO_ENCONTRADO", "Pedido no encontrado"])
  })
  it("en precuenta: PEDIDO_EN_PRECUENTA", () => {
    const e = falla(pedidoCon("precuenta"), agregar())
    expect([e.http, e.codigo, e.message]).toEqual([409, "PEDIDO_EN_PRECUENTA", "La mesa está en precuenta. Reábrela para modificar la comanda."])
  })
  it("cerrado: PEDIDO_CERRADO", () => {
    const e = falla(pedidoCon("cerrado"), agregar())
    expect([e.http, e.codigo, e.message]).toEqual([409, "PEDIDO_CERRADO", "El pedido ya está cerrado"])
  })
})

describe("pedido.modificar_item", () => {
  const mod = (cuerpo: Record<string, unknown>) => cmd("pedido.modificar_item", { item_id: "I1", ...cuerpo })
  it("cambia cantidad y observación (vacía la borra)", () => {
    const base = pedidoCon("abierto", [{ ...itemEn("en_espera"), observacion: "sin sal" }])
    const p = aplicar(base, mod({ cantidad: 3 }), "validar")!
    expect([p.items[0].cantidad, p.items[0].subtotal, p.total, p.items[0].observacion]).toEqual([3, 15000, 15000, "sin sal"])
    expect(aplicar(base, mod({ observacion: "" }), "validar")!.items[0].observacion).toBeNull()
  })
  it("ítem inexistente: ITEM_NO_ENCONTRADO", () => {
    const e = falla(pedidoCon("abierto"), mod({ cantidad: 1 }))
    expect([e.http, e.codigo, e.message]).toEqual([404, "ITEM_NO_ENCONTRADO", "Item no encontrado"])
  })
  it("ítem enviado: ITEM_YA_ENVIADO", () => {
    const e = falla(pedidoCon("abierto", [itemEn("enviado")]), mod({ cantidad: 1 }))
    expect([e.http, e.codigo, e.message]).toEqual([409, "ITEM_YA_ENVIADO", "El ítem ya fue enviado a cocina y no se puede modificar"])
  })
  it("respeta el estado del pedido", () => {
    expect(falla(pedidoCon("precuenta", [itemEn("en_espera")]), mod({ cantidad: 1 })).codigo).toBe("PEDIDO_EN_PRECUENTA")
  })
})

describe("pedido.quitar_item", () => {
  const quitar = () => cmd("pedido.quitar_item", { item_id: "I1" })
  it("quita el ítem y recalcula", () => {
    const p = aplicar(pedidoCon("abierto", [itemEn("en_espera")]), quitar(), "validar")!
    expect([p.items.length, p.total]).toEqual([0, 0])
  })
  it("si no está, queda igual", () => {
    const base = pedidoCon("abierto")
    expect(aplicar(base, quitar(), "validar")!.items).toEqual([])
  })
  it("ítem enviado: ITEM_YA_ENVIADO", () => {
    expect(falla(pedidoCon("abierto", [itemEn("enviado")]), quitar()).codigo).toBe("ITEM_YA_ENVIADO")
  })
})

describe("pedido.enviar_tanda", () => {
  const enviar = () => cmd("pedido.enviar_tanda", {})
  it("pasa los en espera a enviado con la tanda siguiente", () => {
    const p = aplicar(pedidoCon("abierto", [itemEn("en_espera", "A"), itemEn("enviado", "B")]), enviar(), "validar")!
    expect(p.n_tandas).toBe(1)
    expect(p.items.map((i) => [i.estado, i.tanda])).toEqual([["enviado", 1], ["enviado", 1]])
  })
  it("sin ítems en espera no cambia", () => {
    const base = pedidoCon("abierto", [itemEn("enviado")])
    expect(aplicar(base, enviar(), "validar")!.n_tandas).toBe(0)
  })
  it("en precuenta: PEDIDO_EN_PRECUENTA", () => {
    expect(falla(pedidoCon("precuenta"), enviar()).codigo).toBe("PEDIDO_EN_PRECUENTA")
  })
})

describe("pedido.precuenta y pedido.reabrir", () => {
  const precuenta = () => cmd("pedido.precuenta", {})
  const reabrir = (confirmado?: boolean) => cmd("pedido.reabrir", { confirmado })
  it("precuenta desde abierto", () => {
    expect(aplicar(pedidoCon("abierto", [itemEn("enviado")]), precuenta(), "validar")!.estado).toBe("precuenta")
  })
  it("precuenta sin consumo: PEDIDO_VACIO", () => {
    const e = falla(pedidoCon("abierto"), precuenta())
    expect([e.http, e.codigo, e.message]).toEqual([422, "PEDIDO_VACIO", "La mesa no tiene consumo"])
  })
  it("precuenta de un pedido cerrado: PEDIDO_CERRADO; ya en precuenta: sin cambios", () => {
    expect(falla(pedidoCon("cerrado"), precuenta()).codigo).toBe("PEDIDO_CERRADO")
    const base = pedidoCon("precuenta")
    expect(aplicar(base, precuenta(), "validar")).toEqual(base)
  })
  it("reabrir exige confirmación", () => {
    const e = falla(pedidoCon("precuenta"), reabrir())
    expect([e.http, e.codigo, e.message]).toEqual([422, "CONFIRMACION_REQUERIDA", "Reabrir la mesa deja sin efecto la precuenta. Confirma para continuar."])
    expect(aplicar(pedidoCon("precuenta"), reabrir(true), "validar")!.estado).toBe("abierto")
  })
  it("reabrir un pedido cerrado: PEDIDO_CERRADO", () => {
    expect(falla(pedidoCon("cerrado"), reabrir(true)).codigo).toBe("PEDIDO_CERRADO")
  })
})

describe("modo superponer", () => {
  it("nunca lanza: devuelve el pedido sin cambios", () => {
    const base = pedidoCon("precuenta")
    expect(aplicar(base, agregar(), "superponer")).toBe(base)
    expect(aplicar(null, agregar(), "superponer")).toBeNull()
  })
  it("aplicar dos veces el mismo comando es lo mismo que una", () => {
    const base = pedidoCon("abierto")
    const una = aplicar(base, agregar(), "superponer")
    const dos = aplicar(una, agregar(), "superponer")
    expect(dos).toEqual(una)
    const enviar = cmd("pedido.enviar_tanda", {})
    const e1 = aplicar(dos, enviar, "superponer")
    expect(aplicar(e1, enviar, "superponer")).toEqual(e1)
  })
})

describe("huella y estadoMesa", () => {
  it("la huella no depende del orden de los ítems", () => {
    const a = pedidoCon("abierto", [itemEn("en_espera", "A"), itemEn("en_espera", "B")])
    const b = pedidoCon("abierto", [itemEn("en_espera", "B"), itemEn("en_espera", "A")])
    expect(huella(a)).toBe(huella(b))
    expect(huella(null)).toBe("null")
  })
  it("estadoMesa refleja abrir, precuenta y reabrir", () => {
    const mesa: MesaPlano = { mesa_id: "m03", estado: "libre", pedido_id: null, garzon_id: null, sector_id: "s", sector_nombre: "Salón", numero: 3, capacidad: 4 }
    const abierta = estadoMesa(mesa, [abrir()])
    expect([abierta.estado, abierta.pedido_id]).toEqual(["ocupada", "P1"])
    expect(estadoMesa(mesa, [abrir(), cmd("pedido.precuenta", {})]).estado).toBe("precuenta")
    expect(estadoMesa(mesa, [abrir(), cmd("pedido.precuenta", {}), cmd("pedido.reabrir", { confirmado: true })]).estado).toBe("ocupada")
  })
})
