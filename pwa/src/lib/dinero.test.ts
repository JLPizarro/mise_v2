import { describe, expect, it } from "vitest"
import type { Item } from "@/api/tipos"
import { dividirPartesIguales, montoPorItems, propinaSugerida } from "@/lib/dinero"

const item = (item_id: string, cantidad: number, cobrado: number, precio: number): Item => ({
  item_id, producto_id: "p", nombre: "x", categoria: "Fondos", cuarto_id: "c", modificador_id: null,
  modificador_nombre: null, cantidad, cobrado, precio_unitario: precio, subtotal: precio * cantidad,
  estado: "enviado", tanda: 1, observacion: null, creado_en: "", enviado_en: null,
})

describe("propinaSugerida", () => {
  it("redondea como el servidor", () => {
    expect(propinaSugerida(16500, 10)).toBe(1650)
    expect(propinaSugerida(1005, 10)).toBe(101)
  })
})

describe("dividirPartesIguales", () => {
  it("reparte el resto en las primeras partes", () => {
    expect(dividirPartesIguales(100, 3)).toEqual([34, 33, 33])
  })
  it("exige entre 2 y 20 personas", () => {
    expect(() => dividirPartesIguales(100, 1)).toThrow()
    expect(() => dividirPartesIguales(100, 21)).toThrow()
  })
  it("no deja partes en cero", () => {
    expect(() => dividirPartesIguales(2, 3)).toThrow()
  })
})

describe("montoPorItems", () => {
  const items = [item("a", 3, 1, 1000), item("b", 1, 0, 5000)]
  it("usa lo disponible (cantidad - cobrado)", () => {
    expect(montoPorItems(items, [{ item_id: "a", cantidad: 2 }], 99999)).toBe(2000)
  })
  it("topa en el saldo", () => {
    expect(montoPorItems(items, [{ item_id: "b", cantidad: 1 }], 3000)).toBe(3000)
  })
  it("suma las líneas repetidas del mismo ítem", () => {
    expect(montoPorItems(items, [{ item_id: "a", cantidad: 1 }, { item_id: "a", cantidad: 1 }], 99999)).toBe(2000)
  })
  it("falla si excede lo disponible o el ítem no existe", () => {
    expect(() => montoPorItems(items, [{ item_id: "a", cantidad: 3 }], 99999)).toThrow()
    expect(() => montoPorItems(items, [{ item_id: "a", cantidad: 1 }, { item_id: "a", cantidad: 2 }], 99999)).toThrow()
    expect(() => montoPorItems(items, [{ item_id: "z", cantidad: 1 }], 99999)).toThrow()
  })
})
