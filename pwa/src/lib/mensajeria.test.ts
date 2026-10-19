import { describe, expect, it } from "vitest"
import { validarDestino } from "@/lib/mensajeria"

describe("validarDestino", () => {
  it("acepta un destino válido", () => {
    expect(validarDestino({ nombre: "Jefe de turno", tipo: "correo", correo: "jefe@demo.cl", avisos: ["documento_rechazado"] })).toEqual({})
    expect(validarDestino({ nombre: "Contabilidad", tipo: "cola", correo: "", avisos: ["cierre_con_diferencia"] })).toEqual({})
  })
  it("marca cada campo inválido", () => {
    const e = validarDestino({ nombre: "<x>", tipo: "correo", correo: "no", avisos: [] })
    expect(Object.keys(e).sort()).toEqual(["avisos", "correo", "nombre"])
    expect(validarDestino({ nombre: "x".repeat(61), tipo: "cola", correo: "", avisos: ["a"] }).nombre).toBeDefined()
  })
})
