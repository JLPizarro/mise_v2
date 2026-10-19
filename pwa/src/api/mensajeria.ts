import { leer } from "@/api/cliente"
import { crearComando, type Comando } from "@/api/comandos"
import { L } from "@/api/rutas"

/** Administración de la mensajería del local (dueño y admin). Contrato: función `mensajeria` (02, 08). */

export interface EstadoCola { visibles: number; en_proceso: number; no_existe?: boolean }
export interface Canal {
  id: string; tipo: "flujo" | "cola" | "cola_fallidos" | "tema" | "programado"; nombre: string; proposito: string
  productores: string[]; consumidores: string[]; fifo: boolean; max_recepciones: number | null
  fallidos: string | null; tratamiento: string; protegido: boolean; estado?: EstadoCola | null
}
export interface Ruta { evento: string; canal: string; consumidor: string; efecto: string; condicion: string }
export interface AvisoCatalogo { id: string; titulo: string; descripcion: string; canal: string; administrable: boolean }
export interface Catalogo { canales: Canal[]; rutas: Ruta[]; avisos: AvisoCatalogo[] }

export type TipoDestino = "correo" | "cola"
export interface Destino {
  destino_id: string; nombre: string; tipo: TipoDestino; correo: string | null; cola: string | null
  avisos: string[]; reglas: { aviso: string; titulo: string }[]; creado_en: string; creado_por: string
  estado?: "activa" | "pendiente_confirmacion" | "no_existe" | "desconocido"
}
export interface ListaDestinos { destinos: Destino[]; limite: number; avisos_disponibles: { id: string; titulo: string }[] }
export interface MensajeDestino { mensaje_id: string; texto: string; atributos: Record<string, string>; enviado_en: string | null }
export interface ResultadoPrueba {
  aviso: string; mensaje_id: string; atributos: Record<string, string>
  destinos_esperados: { destino_id: string; nombre: string; tipo: TipoDestino }[]; explicacion: string
}
export type OrigenFallo = "proveedor" | "aws" | "negocio" | "codigo"
export interface Diagnostico {
  consumidor: string; canal: string; mensaje_id: string; intento: number; origen?: OrigenFallo; error_tipo: string; error_mensaje: string
  referencia: string; recuperable: boolean; registrado_en: string
}
export interface Fallido {
  canal: "dte-emision" | "contingencia-comandas"; cola_fallidos: string; mensaje_id: string; resumen: string
  enviado_en: string | null; cuerpo: unknown; diagnostico: Diagnostico | null
}
export interface ListaFallidos { fallidos: Fallido[]; errores_recientes: Diagnostico[] }

const M = (localId: string) => `${L(localId)}/mensajeria`

export const catalogo = (localId: string): Promise<Catalogo> => leer(`${M(localId)}/canales`)
export const destinos = (localId: string): Promise<ListaDestinos> => leer(`${M(localId)}/destinos`)
export const mensajesDeDestino = (localId: string, destinoId: string): Promise<{ mensajes: MensajeDestino[] }> =>
  leer(`${M(localId)}/destinos/${destinoId}/mensajes`)
export const fallidos = (localId: string): Promise<ListaFallidos> => leer(`${M(localId)}/fallidos`)

export const crearDestino = (
  localId: string, datos: { nombre: string; tipo: TipoDestino; correo?: string; avisos: string[] },
): Comando => crearComando(localId, "POST", `${M(localId)}/destinos`, { ...datos })

export const eliminarDestino = (localId: string, destinoId: string): Comando =>
  crearComando(localId, "DELETE", `${M(localId)}/destinos/${destinoId}`, {})

export const crearRegla = (localId: string, destinoId: string, aviso: string): Comando =>
  crearComando(localId, "POST", `${M(localId)}/destinos/${destinoId}/reglas`, { aviso })

export const eliminarRegla = (localId: string, destinoId: string, aviso: string): Comando =>
  crearComando(localId, "DELETE", `${M(localId)}/destinos/${destinoId}/reglas/${encodeURIComponent(aviso)}`, {})

export const enviarPrueba = (localId: string, aviso: string): Comando =>
  crearComando(localId, "POST", `${M(localId)}/pruebas`, { aviso })

export const reprocesarFallido = (localId: string, f: Fallido): Comando =>
  crearComando(localId, "POST", `${M(localId)}/fallidos/${f.mensaje_id}/reprocesar`, { canal: f.canal })

export const descartarFallido = (localId: string, f: Fallido): Comando =>
  crearComando(localId, "POST", `${M(localId)}/fallidos/${f.mensaje_id}/descartar`, { canal: f.canal })
