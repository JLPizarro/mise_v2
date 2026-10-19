export type Rol = "dueno" | "admin" | "cajero" | "garzon" | "cocina"
export type EstadoMesa = "libre" | "ocupada" | "precuenta" | "bloqueada"
export type EstadoPedido = "abierto" | "precuenta" | "cerrado"
export type EstadoItem = "en_espera" | "enviado"
export type MetodoPago = "efectivo" | "debito" | "credito" | "transferencia"
export type TipoDivision = "completa" | "items" | "partes_iguales" | "monto_libre"
export type TipoDocumento = "boleta" | "factura"
export type Categoria = "Entradas" | "Fondos" | "Bebidas" | "Postres"
export type Unidad = "kg" | "g" | "l" | "ml" | "unidad"

export interface LocalDeUsuario {
  tenant_id: string; local_id: string; rol: Rol; nombre_local: string; marca: string
  propina_sugerida_pct: number; estaciones_caja: string[]; puede_autorizar: boolean
}
export interface Yo { sub: string; email: string; nombre: string; locales: LocalDeUsuario[] }

export interface Sector { sector_id: string; nombre: string; activo: boolean }
export interface MesaPlano {
  mesa_id: string; estado: EstadoMesa; pedido_id: string | null; garzon_id: string | null
  sector_id: string; sector_nombre: string; numero: number; capacidad: number
}
export interface Plano { mesas: MesaPlano[]; sectores: Sector[] }
export interface EstadoMesaSolo { mesa_id: string; estado: EstadoMesa; pedido_id: string | null; garzon_id: string | null }

export interface Modificador { modificador_id: string; nombre: string; precio_adicional: number }
export interface Producto {
  producto_id: string; nombre: string; categoria: Categoria; precio: number; cuarto_id: string
  activo: boolean; descripcion: string | null; modificadores: Modificador[]
}
export interface Carta { version: number; productos: Producto[] }

export interface Item {
  item_id: string; producto_id: string; nombre: string; categoria: Categoria; cuarto_id: string
  modificador_id: string | null; modificador_nombre: string | null; cantidad: number; cobrado: number
  precio_unitario: number; subtotal: number; estado: EstadoItem; tanda: number | null
  observacion: string | null; creado_en: string; enviado_en: string | null
}
export interface Pago {
  pago_id: string; turno_id: string; metodo: MetodoPago; monto: number; propina: number
  tipo_division: TipoDivision; codigo_autorizacion_pos: string | null; efectivo_recibido: number | null
  vuelto: number | null; items_cobrados: { item_id: string; cantidad: number }[]; usuario_id: string; fecha: string
}
export interface Pedido {
  pedido_id: string; mesa_id: string; garzon_id: string; estado: EstadoPedido; total: number
  pagado: number; saldo: number; propina_total: number; n_tandas: number
  documento: { tipo: TipoDocumento; receptor?: { rut: string; razon_social: string } } | null
  creado_en: string; cerrado_en: string | null; items: Item[]; pagos: Pago[]
}
export interface Impresion { cuarto_id: string; cuarto: string; estado: "encolada" | "sin_impresora" | "retenida_contingencia" }

export interface Turno {
  turno_id: string; estado: "abierto" | "cerrado"; monto_apertura: number; usuario_apertura_id: string
  abierto_en: string; fecha_operativa: string; primer_conteo: number | null; segundo_conteo: number | null
  requiere_segundo_conteo: boolean
  conciliacion: { total_debito_pos: number; total_credito_pos: number; total_notas_credito_pos: number } | null
  usuario_cierre_id: string | null; cerrado_en: string | null; resultado?: ResultadoCierre
}
export interface ResultadoCierre {
  efectivo_esperado: number; conteo_definitivo: number; diferencia_efectivo: number
  total_efectivo_mise: number; total_debito_mise: number; total_credito_mise: number
  total_transferencia_mise: number; total_retiros: number; umbral: number; fuera_de_umbral: boolean
  n_ventas: number; total_ventas: number
}
export interface Retiro { retiro_id: string; turno_id: string; usuario_id: string; autorizado_por: string; monto: number; motivo: string; creado_en: string }
export interface Autorizador { sub: string; nombre: string; rol: Rol }
export interface Documento {
  venta_id: string; turno_id: string; estado: "pendiente" | "enviando" | "emitido" | "rechazado" | "fallido"
  tipo: TipoDocumento; receptor: { rut: string; razon_social: string } | null; total: number
  folio: number | null; timbre: string | null; motivo_rechazo: string | null; intentos: number
  creado_en: string; emitido_en: string | null
}
export interface Conflicto {
  conflicto_id: string; estado: "abierto" | "resuelto" | "descartado"; motivo: string; codigo_rechazo: string
  operacion: string; creado_en: string; nota?: string; resuelto_por?: string; resuelto_en?: string
  comando: { command_id: string; local_id: string; grupo: string; operacion: string; cuerpo: Record<string, unknown>; ocurrido_en: string; entrada: "servidor" | "cliente"; nombre: string }
}
export interface TrabajoRetenido {
  trabajo_id: string; tipo: string; impresora_id: string; pedido_id: string; tanda: number; mesa_id: string
  mesa_numero: number | null; sector: string | null; cuarto: string; garzon: string; creado_en: string
  lineas: { cantidad: number; nombre: string; modificador: string | null; observacion: string | null }[]
}
