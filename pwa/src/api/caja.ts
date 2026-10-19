import { ErrorApi, leer } from "@/api/cliente"
import { crearComando, type Comando } from "@/api/comandos"
import { L } from "@/api/rutas"
import type {
  Autorizador, Conflicto, Documento, MetodoPago, Pago, Pedido, Retiro, TipoDivision, TipoDocumento,
  TrabajoRetenido, Turno,
} from "@/api/tipos"

// --- lecturas -------------------------------------------------------------------------------------

/** 404 TURNO_NO_ABIERTO significa «sin turno», no es un error. */
export async function turnoActual(localId: string): Promise<Turno | null> {
  try {
    return await leer<Turno>(`${L(localId)}/caja/turno`)
  } catch (e) {
    if (e instanceof ErrorApi && e.codigo === "TURNO_NO_ABIERTO") return null
    throw e
  }
}

export const pendientes = (localId: string): Promise<{ pendientes: { mesa_id: string; pedido: Pedido }[] }> =>
  leer(`${L(localId)}/caja/pendientes`)

export const documentos = (localId: string, turnoId?: string): Promise<{ turno_id: string; documentos: Documento[] }> =>
  leer(`${L(localId)}/caja/documentos`, { turno_id: turnoId })

export const documento = (localId: string, ventaId: string): Promise<Documento> =>
  leer(`${L(localId)}/caja/documentos/${ventaId}`)

export const autorizadores = (localId: string): Promise<{ autorizadores: Autorizador[] }> =>
  leer(`${L(localId)}/caja/autorizadores`)

export const retiros = (localId: string, turnoId?: string): Promise<{ turno_id: string; retiros: Retiro[] }> =>
  leer(`${L(localId)}/caja/retiros`, { turno_id: turnoId })

export const conflictos = (localId: string, todos = false): Promise<{ conflictos: Conflicto[] }> =>
  leer(`${L(localId)}/caja/conflictos`, { todos: todos ? "1" : undefined })

export const impresionesRetenidas = (localId: string): Promise<{ trabajos: TrabajoRetenido[] }> =>
  leer(`${L(localId)}/caja/impresiones-retenidas`)

// --- escrituras (cada una es un Comando; se ejecuta con `escribir`) -------------------------------------

export const abrirTurno = (localId: string, montoApertura: number): Comando =>
  crearComando(localId, "POST", `${L(localId)}/caja/turnos`, { monto_apertura: montoApertura })

export const conteo = (localId: string, turnoId: string, monto: number): Comando =>
  crearComando(localId, "POST", `${L(localId)}/caja/turnos/${turnoId}/conteo`, { turno_id: turnoId, monto })

export const conciliacion = (
  localId: string, turnoId: string,
  total: { total_debito_pos: number; total_credito_pos: number; total_notas_credito_pos: number },
): Comando => crearComando(localId, "POST", `${L(localId)}/caja/turnos/${turnoId}/conciliacion`, { turno_id: turnoId, ...total })

export const cerrarTurno = (localId: string, turnoId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/caja/turnos/${turnoId}/cerrar`, { turno_id: turnoId })

export interface Medio {
  metodo: MetodoPago
  monto: number
  propina?: number
  codigo_autorizacion_pos?: string
  efectivo_recibido?: number
}

export interface RespuestaPago {
  pagos: Pago[]
  pedido: { pedido_id: string; total: number; pagado: number; saldo: number; propina_total: number }
}

/** Un solo comando con 1 o 2 medios. `items_cobrados` solo con `tipo_division = "items"`. */
export const registrarPago = (
  localId: string, pedidoId: string,
  datos: { medios: Medio[]; tipo_division: TipoDivision; items_cobrados?: { item_id: string; cantidad: number }[] },
): Comando => crearComando(localId, "POST", `${L(localId)}/pedidos/${pedidoId}/pagos`, {
  pedido_id: pedidoId, medios: datos.medios, tipo_division: datos.tipo_division,
  items_cobrados: datos.tipo_division === "items" ? datos.items_cobrados : undefined,
})

/** Con total = 0 se envía solo `{pedido_id}` (liberar la mesa sin consumo). */
export const finalizar = (
  localId: string, pedidoId: string,
  datos?: { tipo_documento: TipoDocumento; receptor?: { rut: string; razon_social: string } },
): Comando => crearComando(localId, "POST", `${L(localId)}/pedidos/${pedidoId}/finalizar`, {
  pedido_id: pedidoId, tipo_documento: datos?.tipo_documento, receptor: datos?.receptor,
})

export const reimprimir = (localId: string, ventaId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/caja/documentos/${ventaId}/reimprimir`, { venta_id: ventaId })

export const registrarRetiro = (
  localId: string, datos: { monto: number; motivo: string; autorizador_id: string; codigo: string },
): Comando => crearComando(localId, "POST", `${L(localId)}/caja/retiros`, datos)

export const resolverConflicto = (
  localId: string, conflictoId: string, resolucion: "resuelto" | "descartado", nota?: string,
): Comando => crearComando(localId, "POST", `${L(localId)}/caja/conflictos/${conflictoId}/resolver`, {
  conflicto_id: conflictoId, resolucion, nota: nota || undefined,
})

export const liberarImpresion = (localId: string, trabajoId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/caja/impresiones-retenidas/${trabajoId}/liberar`, { trabajo_id: trabajoId })

export const descartarImpresion = (localId: string, trabajoId: string): Comando =>
  crearComando(localId, "POST", `${L(localId)}/caja/impresiones-retenidas/${trabajoId}/descartar`, { trabajo_id: trabajoId })
