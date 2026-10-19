import { leer } from "@/api/cliente"
import { L } from "@/api/rutas"
import type { Retiro, Turno } from "@/api/tipos"

export interface ResumenTurnoFila {
  turno_id: string; fecha_operativa: string; estado: string; abierto_en: string
  cerrado_en?: string; diferencia_efectivo?: number; total_ventas?: number
}

export interface DetalleTurno {
  turno: Turno & { efectivo_esperado?: number }
  caja: {
    efectivo: number; debito: number; credito: number; transferencia: number; retiros: number
    n_pagos: number; n_ventas: number; total_ventas: number
  }
  resumen: { n_ventas?: number; total_ventas?: number; total_propinas?: number; n_retiros?: number; total_retiros?: number }
  por_garzon: { garzon_id: string; n_ventas: number; total_ventas: number; total_propinas: number }[]
  retiros: Retiro[]
  documentos: Record<string, number>
}

export interface ResumenDia {
  fecha: string
  resumen: { n_ventas?: number; total_ventas?: number; total_propinas?: number; n_cerrados_sin_venta?: number }
}

export const turnos = (localId: string, desde: string, hasta: string): Promise<{ turnos: ResumenTurnoFila[] }> =>
  leer(`${L(localId)}/reportes/turnos`, { desde, hasta })

export const turno = (localId: string, turnoId: string): Promise<DetalleTurno> =>
  leer(`${L(localId)}/reportes/turnos/${turnoId}`)

export const dia = (localId: string, fecha: string): Promise<ResumenDia> =>
  leer(`${L(localId)}/reportes/dias/${fecha}`)
