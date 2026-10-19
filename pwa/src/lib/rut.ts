export const normalizarRut = (t: string): string => t.replace(/[.\s]/g, "").toUpperCase()
export const rutValido = (t: string): boolean => /^\d{7,8}-[\dK]$/.test(normalizarRut(t))

/** Factura: RUT válido y razón social de 2 a 200 caracteres. */
export const facturaValida = (rut: string, razonSocial: string): boolean =>
  rutValido(rut) && razonSocial.trim().length >= 2 && razonSocial.trim().length <= 200
