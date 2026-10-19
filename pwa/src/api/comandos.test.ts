import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ErrorApi, SinConexion } from "@/api/cliente"
import { crearComando, ejecutar } from "@/api/comandos"
import { cola } from "@/offline/cola"
import { red } from "@/offline/red"
import { sincronizacion } from "@/offline/sincronizar"
import { cabecera, cuerpoEnviado, prepararEntorno, respuesta, rutasLlamadas, simularFetch } from "@/test/ayudas"

const LOCAL = "local_01"
const agregar = () =>
  crearComando(LOCAL, "POST", `/locales/${LOCAL}/pedidos/P1/items`,
    { pedido_id: "P1", mesa_id: "m03", item_id: "I1", producto_id: "pr1", cantidad: 1 }, "pedido.agregar_item")
const cobrar = () => crearComando(LOCAL, "POST", `/locales/${LOCAL}/caja/turnos`, { monto_apertura: 1000 })

/** Corre la promesa dejando avanzar los temporizadores (esperas de 300 ms y 1 s). */
async function correr<T>(p: Promise<T>): Promise<{ ok?: T; error?: unknown }> {
  const resultado = p.then((ok) => ({ ok }), (error: unknown) => ({ error }))
  await vi.advanceTimersByTimeAsync(5000)
  return resultado
}

beforeEach(async () => {
  await prepararEntorno("mock-garzon")
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
})
afterEach(() => {
  vi.useRealTimers()
})

describe("ejecutar", () => {
  it("un 409 de negocio lanza sin reintentar", async () => {
    const f = simularFetch(respuesta(409, { codigo: "PEDIDO_EN_PRECUENTA", mensaje: "En precuenta" }))
    const { error } = await correr(ejecutar(agregar()))
    expect(error).toBeInstanceOf(ErrorApi)
    expect(f).toHaveBeenCalledTimes(1)
  })

  it("CONFLICTO_CONCURRENCIA se reintenta una vez con el mismo ID", async () => {
    const f = simularFetch(respuesta(409, { codigo: "CONFLICTO_CONCURRENCIA", mensaje: "x" }), respuesta(201, { ok: 1 }))
    const c = agregar()
    const { ok } = await correr(ejecutar(c))
    expect(ok?.via).toBe("normal")
    expect(f).toHaveBeenCalledTimes(2)
    expect(cabecera(f, 0, "X-Command-Id")).toBe(c.id)
    expect(cabecera(f, 1, "X-Command-Id")).toBe(c.id)
  })

  it("503 dos veces en una comanda va a /contingencia/comandas con el mismo ID", async () => {
    const f = simularFetch(respuesta(503, { message: "x" }), respuesta(503, { message: "x" }),
      respuesta(202, { estado: "aceptada_en_contingencia", command_id: "x" }))
    const c = agregar()
    const { ok } = await correr(ejecutar(c))
    expect(ok?.via).toBe("contingencia")
    expect(rutasLlamadas(f)).toEqual([c.ruta, c.ruta, "/contingencia/comandas"])
    expect(cuerpoEnviado(f, 2)).toEqual({ operacion: "pedido.agregar_item", local_id: LOCAL, cuerpo: c.cuerpo, ocurrido_en: c.creadoEn })
    expect(cabecera(f, 2, "X-Command-Id")).toBe(c.id)
    expect(sincronizacion.activa(LOCAL, "m03")).toBe(true)
  })

  it("503 dos veces en una escritura que no es comanda lanza", async () => {
    const f = simularFetch(respuesta(503, { message: "x" }))
    const { error } = await correr(ejecutar(cobrar()))
    expect(error).toBeInstanceOf(ErrorApi)
    expect(f).toHaveBeenCalledTimes(2)
  })

  it("contingencia caída en la estación guarda en la cola local", async () => {
    localStorage.setItem(`pos.estacion.${LOCAL}`, "est_01")
    simularFetch(respuesta(503, { message: "x" }))
    const { ok } = await correr(ejecutar(agregar()))
    expect(ok?.via).toBe("cola_local")
    expect(await cola.contar(LOCAL)).toBe(1)
  })

  it("contingencia caída sin estación lanza «usa la caja»", async () => {
    simularFetch(respuesta(503, { message: "x" }))
    const { error } = await correr(ejecutar(agregar()))
    expect(error).toBeInstanceOf(SinConexion)
    expect((error as Error).message).toBe("Sin conexión: usa la caja")
    expect(await cola.contar(LOCAL)).toBe(0)
  })

  it("estación sin conexión guarda en la cola sin llamar a fetch", async () => {
    localStorage.setItem(`pos.estacion.${LOCAL}`, "est_01")
    const f = simularFetch(respuesta(200))
    red.reportarFalla()
    const { ok } = await correr(ejecutar(agregar()))
    expect(ok?.via).toBe("cola_local")
    expect(f).not.toHaveBeenCalled()
  })

  it("con comandas ya guardadas, la estación sigue guardando en orden aunque haya conexión", async () => {
    localStorage.setItem(`pos.estacion.${LOCAL}`, "est_01")
    const f = simularFetch(respuesta(200))
    await cola.agregar(agregar())
    const { ok } = await correr(ejecutar(agregar()))
    expect(ok?.via).toBe("cola_local")
    expect(f).not.toHaveBeenCalled()
    expect(await cola.contar(LOCAL)).toBe(2)
  })

  it("un 202 del servidor es contingencia y deja la mesa sincronizando", async () => {
    simularFetch(respuesta(202, { estado: "aceptada_en_contingencia", command_id: "x" }))
    const { ok } = await correr(ejecutar(agregar()))
    expect(ok?.via).toBe("contingencia")
    expect(sincronizacion.activa(LOCAL, "m03")).toBe(true)
  })

  it("una mesa sincronizando manda sus comandas nuevas por contingencia", async () => {
    sincronizacion.registrar(agregar())
    const f = simularFetch(respuesta(202, { estado: "aceptada_en_contingencia", command_id: "x" }))
    const { ok } = await correr(ejecutar(agregar()))
    expect(ok?.via).toBe("contingencia")
    expect(rutasLlamadas(f)).toEqual(["/contingencia/comandas"])
  })
})
