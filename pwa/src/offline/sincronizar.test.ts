import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { crearComando } from "@/api/comandos"
import type { Pedido } from "@/api/tipos"
import { cola } from "@/offline/cola"
import { ESPERA_MAXIMA_MS, sincronizacion, vaciarCola } from "@/offline/sincronizar"
import { cabecera, prepararEntorno, respuesta, rutasLlamadas, simularFetch } from "@/test/ayudas"

const LOCAL = "local_01"
const abrir = (mesa: string) =>
  crearComando(LOCAL, "POST", `/locales/${LOCAL}/pedidos`, { mesa_id: mesa, pedido_id: `P-${mesa}` }, "pedido.abrir")
const agregar = () =>
  crearComando(LOCAL, "POST", `/locales/${LOCAL}/pedidos/P1/items`,
    { pedido_id: "P1", mesa_id: "m03", item_id: "I1", producto_id: "pr", cantidad: 2 }, "pedido.agregar_item",
    { nombre: "Pizza", categoria: "Fondos", cuarto_id: "cu", precio_unitario: 5000, modificador_nombre: null })
const aceptada = () => respuesta(202, { estado: "aceptada_en_contingencia", command_id: "x" })

const pedidoServidor = (items: Pedido["items"]): Pedido => ({
  pedido_id: "P1", mesa_id: "m03", garzon_id: "g", estado: "abierto", total: 0, pagado: 0, saldo: 0, propina_total: 0,
  n_tandas: 0, documento: null, creado_en: "", cerrado_en: null, items, pagos: [],
})

beforeEach(() => prepararEntorno("mock-cajero"))
afterEach(() => vi.useRealTimers())

describe("vaciarCola", () => {
  it("envía por contingencia, en orden, de a uno", async () => {
    const [a, b, c] = [abrir("m01"), abrir("m02"), abrir("m03")]
    for (const x of [a, b, c]) await cola.agregar(x)
    const f = simularFetch(aceptada)
    expect(await vaciarCola(LOCAL)).toBe(3)
    expect(rutasLlamadas(f)).toEqual(Array(3).fill("/contingencia/comandas"))
    expect([0, 1, 2].map((n) => cabecera(f, n, "X-Command-Id"))).toEqual([a.id, b.id, c.id])
    expect(await cola.contar(LOCAL)).toBe(0)
    expect(sincronizacion.activa(LOCAL, "m02")).toBe(true)
  })

  it("se detiene ante un 503 y deja el resto en la cola", async () => {
    for (const m of ["m01", "m02", "m03"]) await cola.agregar(abrir(m))
    simularFetch(aceptada, respuesta(503, { message: "x" }))
    expect(await vaciarCola(LOCAL)).toBe(1)
    expect(await cola.contar(LOCAL)).toBe(2)
  })

  it("se detiene si la sesión vence", async () => {
    for (const m of ["m01", "m02", "m03"]) await cola.agregar(abrir(m))
    simularFetch(aceptada, respuesta(401, { message: "Unauthorized" }))
    expect(await vaciarCola(LOCAL)).toBe(1)
    expect(await cola.contar(LOCAL)).toBe(2)
  })

  it("un 4xx va a rechazados y sigue con el resto", async () => {
    for (const m of ["m01", "m02", "m03"]) await cola.agregar(abrir(m))
    simularFetch(aceptada, respuesta(422, { codigo: "CAMPO_INVALIDO", mensaje: "Campo inválido" }), aceptada)
    expect(await vaciarCola(LOCAL)).toBe(2)
    expect(await cola.contar(LOCAL)).toBe(0)
    const rechazados = await cola.rechazados(LOCAL)
    expect(rechazados.map((r) => r.codigo)).toEqual(["CAMPO_INVALIDO"])
  })

  it("sin sesión no envía nada", async () => {
    await cola.agregar(abrir("m01"))
    const { cerrarSesion } = await import("@/sesion/google")
    cerrarSesion()
    const f = simularFetch(aceptada)
    expect(await vaciarCola(LOCAL)).toBe(0)
    expect(f).not.toHaveBeenCalled()
  })
})

describe("verificar", () => {
  const itemDelServidor = {
    item_id: "I1", producto_id: "pr", nombre: "Pizza", categoria: "Fondos" as const, cuarto_id: "cu", modificador_id: null,
    modificador_nombre: null, cantidad: 2, cobrado: 0, precio_unitario: 5000, subtotal: 10000,
    estado: "en_espera" as const, tanda: null, observacion: null, creado_en: "", enviado_en: null,
  }
  function simularServidor(pedido: Pedido, conflictos: unknown[] = []) {
    const f = vi.fn(async (url: string) =>
      url.includes("/caja/conflictos") ? respuesta(200, { conflictos }) : respuesta(200, pedido))
    vi.stubGlobal("fetch", f)
    return f
  }

  it("termina cuando el pedido del servidor ya refleja los comandos", async () => {
    sincronizacion.registrar(agregar())
    simularServidor(pedidoServidor([itemDelServidor]))
    await sincronizacion.verificar(() => {})
    expect(sincronizacion.activa(LOCAL, "m03")).toBe(false)
  })

  it("sigue sincronizando mientras el servidor no lo refleje", async () => {
    sincronizacion.registrar(agregar())
    simularServidor(pedidoServidor([]))
    const aviso = vi.fn()
    await sincronizacion.verificar(aviso)
    expect(sincronizacion.activa(LOCAL, "m03")).toBe(true)
    expect(aviso).not.toHaveBeenCalled()
  })

  it("quita los comandos que tienen conflicto", async () => {
    const c = agregar()
    sincronizacion.registrar(c)
    simularServidor(pedidoServidor([]), [{ comando: { command_id: c.id } }])
    await sincronizacion.verificar(() => {})
    expect(sincronizacion.activa(LOCAL, "m03")).toBe(false)
  })

  it("avisa y suelta la mesa a los 120 s", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    sincronizacion.registrar(agregar())
    simularServidor(pedidoServidor([]))
    vi.setSystemTime(Date.now() + ESPERA_MAXIMA_MS + 1000)
    const aviso = vi.fn()
    await sincronizacion.verificar(aviso)
    expect(aviso).toHaveBeenCalledWith(expect.stringContaining("m03"))
    expect(sincronizacion.activa(LOCAL, "m03")).toBe(false)
  })
})
