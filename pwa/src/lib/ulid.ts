const B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

export function ulid(ahora: number = Date.now()): string {
  let tiempo = ""
  let t = ahora
  for (let i = 0; i < 10; i++) {
    tiempo = B32[t % 32] + tiempo
    t = Math.floor(t / 32)
  }
  const azar = crypto.getRandomValues(new Uint8Array(16))
  let resto = ""
  for (const byte of azar) resto += B32[byte & 31]
  return tiempo + resto
}

export const esUlid = (valor: string): boolean => /^[0-7][0-9A-HJKMNP-TV-Z]{25}$/.test(valor)
