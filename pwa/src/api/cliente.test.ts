import { beforeEach, describe, expect, it } from "vitest"
import { ErrorApi, pedir, SesionRequerida, SinConexion } from "@/api/cliente"
import { cerrarSesion, estadoSesion, ingresarDev, tokenVigente } from "@/sesion/google"
import { cabecera, prepararEntorno, respuesta, simularFetch } from "@/test/ayudas"

beforeEach(() => prepararEntorno())

describe("pedir", () => {
  it("envía Authorization siempre y X-Command-Id / Content-Type solo cuando corresponde", async () => {
    const f = simularFetch(() => respuesta(200, { ok: true }))
    await pedir("GET", "/yo")
    expect(cabecera(f, 0, "Authorization")).toBe("Bearer dev:mock-cajero")
    expect(cabecera(f, 0, "X-Command-Id")).toBeUndefined()
    expect(cabecera(f, 0, "Content-Type")).toBeUndefined()

    await pedir("POST", "/x", { cuerpo: { a: 1 }, commandId: "ID1" })
    expect(cabecera(f, 1, "X-Command-Id")).toBe("ID1")
    expect(cabecera(f, 1, "Content-Type")).toBe("application/json")
  })

  it("una ruta pública no envía Authorization", async () => {
    const f = simularFetch(() => respuesta(200, { estado: "ok" }))
    await pedir("GET", "/salud", { publica: true })
    expect(cabecera(f, 0, "Authorization")).toBeUndefined()
  })

  it("401 vence la sesión y lanza SesionRequerida", async () => {
    simularFetch(respuesta(401, { message: "Unauthorized" }))
    await expect(pedir("GET", "/yo")).rejects.toBeInstanceOf(SesionRequerida)
    expect(tokenVigente()).toBeNull()
  })

  it("en el último minuto del token se marca la sesión vencida", async () => {
    const f = simularFetch(() => respuesta(200))
    ingresarDev("mock-cajero", 30_000) // vence en 30 s: dentro del último minuto
    await expect(pedir("GET", "/yo")).rejects.toBeInstanceOf(SesionRequerida)
    expect(estadoSesion().token).toBeNull()
    expect(f).not.toHaveBeenCalled()
  })

  it("sin token no llama a la red", async () => {
    const f = simularFetch(() => respuesta(200))
    cerrarSesion()
    await expect(pedir("GET", "/yo")).rejects.toBeInstanceOf(SesionRequerida)
    expect(f).not.toHaveBeenCalled()
  })

  it("un error de la Lambda llega como ErrorApi con codigo, mensaje y detalle", async () => {
    simularFetch(respuesta(409, { codigo: "MONTO_EXCEDE_SALDO", mensaje: "Excede el saldo", requestId: "r1", detalle: { saldo: 500 } }))
    const error = await pedir("POST", "/x", { cuerpo: {} }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ErrorApi)
    const e = error as ErrorApi
    expect([e.http, e.codigo, e.message, e.detalle, e.requestId]).toEqual([409, "MONTO_EXCEDE_SALDO", "Excede el saldo", { saldo: 500 }, "r1"])
    expect(e.esFallaDeServicio).toBe(false)
  })

  it("503 y 429 del API Gateway son falla de servicio", async () => {
    simularFetch(respuesta(503, { message: "Service Unavailable" }))
    const e = (await pedir("GET", "/yo").catch((x: unknown) => x)) as ErrorApi
    expect(e.esFallaDeServicio).toBe(true)
    expect(e.codigo).toBe("HTTP_503")
  })

  it("un error de fetch es SinConexion", async () => {
    simularFetch(new TypeError("Failed to fetch"))
    await expect(pedir("GET", "/yo")).rejects.toBeInstanceOf(SinConexion)
  })

  it("x-comando-repetido marca repetido", async () => {
    simularFetch(respuesta(200, {}, { "x-comando-repetido": "true" }))
    expect((await pedir("POST", "/x", { cuerpo: {}, commandId: "ID" })).repetido).toBe(true)
  })
})
