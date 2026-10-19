import { beforeEach, describe, expect, it } from "vitest"
import { crearComando } from "@/api/comandos"
import { cola } from "@/offline/cola"
import { prepararEntorno } from "@/test/ayudas"

const cmd = (local: string, mesa: string) =>
  crearComando(local, "POST", `/locales/${local}/pedidos`, { mesa_id: mesa, pedido_id: `P-${mesa}` }, "pedido.abrir")

beforeEach(() => prepararEntorno("mock-cajero"))

describe("cola local", () => {
  it("devuelve los comandos en orden de llegada (seq)", async () => {
    const a = cmd("L1", "m01"), b = cmd("L1", "m02"), c = cmd("L1", "m03")
    await cola.agregar(a)
    await cola.agregar(b)
    await cola.agregar(c)
    expect((await cola.pendientes("L1")).map((g) => g.id)).toEqual([a.id, b.id, c.id])
  })

  it("el mismo ID dos veces es una sola entrada", async () => {
    const a = cmd("L1", "m01")
    await cola.agregar(a)
    await cola.agregar(a)
    expect(await cola.contar("L1")).toBe(1)
  })

  it("cuenta por local", async () => {
    await cola.agregar(cmd("L1", "m01"))
    await cola.agregar(cmd("L2", "m01"))
    expect(await cola.contar("L1")).toBe(1)
    expect(await cola.contar("L2")).toBe(1)
  })

  it("registra quién guardó el comando", async () => {
    await cola.agregar(cmd("L1", "m01"))
    expect((await cola.pendientes("L1"))[0].registradoPor).toEqual({ sub: "mock-cajero", nombre: "mock-cajero" })
  })

  it("rechazar mueve el comando a rechazados", async () => {
    const a = cmd("L1", "m01")
    await cola.agregar(a)
    const [guardado] = await cola.pendientes("L1")
    await cola.rechazar(guardado, "MESA_BLOQUEADA", "La mesa está bloqueada")
    expect(await cola.contar("L1")).toBe(0)
    const rechazados = await cola.rechazados("L1")
    expect(rechazados).toHaveLength(1)
    expect([rechazados[0].id, rechazados[0].codigo, rechazados[0].mensaje]).toEqual([a.id, "MESA_BLOQUEADA", "La mesa está bloqueada"])
    await cola.descartarRechazado(a.id)
    expect(await cola.rechazados("L1")).toHaveLength(0)
  })
})
