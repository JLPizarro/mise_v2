import { describe, expect, it } from "vitest"
import { esUlid, ulid } from "@/lib/ulid"

describe("ulid", () => {
  it("tiene 26 caracteres y cumple esUlid", () => {
    const id = ulid()
    expect(id).toHaveLength(26)
    expect(esUlid(id)).toBe(true)
  })

  it("el prefijo de tiempo crece con la hora", () => {
    const antes = ulid(1_700_000_000_000).slice(0, 10)
    const despues = ulid(1_700_000_001_000).slice(0, 10)
    expect(despues > antes).toBe(true)
  })

  it("rechaza lo que no es ULID", () => {
    expect(esUlid("m01")).toBe(false)
    expect(esUlid("8".repeat(26))).toBe(false)
  })
})
