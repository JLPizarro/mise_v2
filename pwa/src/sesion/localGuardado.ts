const CLAVE = "pos.local_id"

/** El último local elegido (P7). Es una comodidad: si el almacenamiento falla, se pregunta de nuevo. */
export function localGuardado(): string | null {
  try {
    return localStorage.getItem(CLAVE)
  } catch {
    return null
  }
}

export function guardarLocal(localId: string): void {
  try {
    localStorage.setItem(CLAVE, localId)
  } catch {
    /* sin almacenamiento */
  }
}
