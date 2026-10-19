# 07 — Plan de ejecución: PWA v2 (sin backend local)

Plan cerrado para que un agente de código lo ejecute **sin tomar decisiones**. Todo lo que se
decidió está en la sección 2; el contrato con las Lambdas, en la sección 3. Si algo no está cubierto,
el agente se detiene y lo informa: no inventa reglas, rutas ni campos.

---

## 0. Reglas para el agente

1. Trabaja en la rama `feature/migracion-lambdas`, en la carpeta `POS/POS`. Ejecuta las fases en
   orden (sección 9). Al terminar cada fase: pruebas en verde y un commit convencional **con rutas
   explícitas** (nunca `git add -A`, `git add .` ni `git commit -a`). Termina cada mensaje de commit con
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
2. **No modifiques** `lambdas/` (el backend está congelado), ni `mise-frontend/`, `mise-backend/`,
   `mise-basededatos/`, `mise-nginx/`, `docker-compose.yml` ni `aws-upload/`. `mise-frontend/` es solo
   fuente de lectura para copiar.
3. Nunca guardes el token de Google en `localStorage`, `sessionStorage`, IndexedDB ni en logs. Nunca
   registres en consola el encabezado `Authorization`, códigos de autorización ni claves de impresora.
4. Montos: siempre enteros en pesos (CLP). Nunca `parseFloat` para dinero. Cantidades de inventario:
   la API recibe decimales (hasta 3) y devuelve enteros en milésimas (`*_mil`).
5. Textos de la interfaz en español de Chile. Muestra el `mensaje` que devuelve la API tal cual.
6. Antes de cada commit ejecuta los comandos de la sección 8 de esa fase. Si una prueba falla y no
   sabes por qué, detente e informa la salida.
7. Node 22 y npm 10 (ya instalados). Python: `.venv\Scripts\python` (Windows).

---

## 1. Qué se construye

Una PWA React que habla **directo** con el API Gateway (`https://<id>.execute-api.us-east-1.amazonaws.com/prod`),
sin servidor en el local. Se publica en el bucket S3 `pos-sitio-<cuenta>` y se abre en
`https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/index.html`.

| Dispositivo | Con internet | Sin internet |
|---|---|---|
| Celular de garzón | Salón y comanda | No guarda nada: «Sin conexión: usa la caja» |
| PC de caja **registrado como estación** | Todo lo de su rol | Sigue tomando comandas en una **cola local** (IndexedDB); cobros, turno y retiros esperan a que vuelva internet |
| Cualquier equipo de dueño o admin | Administración y reportes | «Sin conexión» |

Además, un **servidor local de desarrollo** (`scripts/servidor_local.py`) emula el API Gateway con las
Lambdas reales y datos simulados en memoria. Con él la PWA se desarrolla y se prueba completa sin
AWS y sin el ID de cliente de Google, que sigue pendiente.

---

## 2. Decisiones cerradas

| # | Decisión | Motivo |
|---|---|---|
| P1 | La PWA vive en `pwa/` (raíz del repo). Se copia y adapta código de `mise-frontend/` (submódulo deprecado, solo lectura) | No tocar el submódulo de otro repositorio |
| P2 | Stack: React 19, TypeScript con `strict: true`, Vite, Tailwind 4, `@base-ui/react`, `lucide-react` (los del frontend anterior). Nuevas: `idb` (IndexedDB). Pruebas: `vitest`, `jsdom`, `fake-indexeddb` | Reciclar; `strict` detecta los campos renombrados |
| P3 | Enrutador con `#` (`createHashRouter`) y `base: "./"` en Vite | El endpoint REST de S3 no tiene documento por defecto (riesgo C2 de 04) |
| P4 | **Sin direcciones en el código**: `config.json` junto a `index.html` con `api_url`, `google_client_id` y `modo_dev`. Lo escribe `publicar_pwa.sh` en la nube; en desarrollo se copia de `pwa/config.example.json` | Cambiar de entorno sin recompilar |
| P5 | Login: Google Identity Services. El ID token vive solo en memoria; renovación silenciosa 5 min antes de vencer. En la estación de caja, `auto_select: false` (selección manual de cuenta) | 00-inventario §7 |
| P6 | `modo_dev: true` solo con el servidor local: botones «Entrar como mock-…» que envían `Authorization: Bearer dev:<sub>`. El API Gateway real rechaza ese token, así que no abre nada en la nube | Probar sin Google |
| P7 | Identidad y rol salen de `GET /yo`; el local va en la URL (`#/l/:localId/...`). Si hay más de un local, se elige; el último elegido se recuerda en `localStorage` (`pos.local_id`) | P6/P7 de la migración: dueño con varios locales |
| P8 | Cada intención del usuario crea **un** comando con `X-Command-Id` (ULID) y un cuerpo **congelado**. Reintentos, contingencia y cola local reutilizan el mismo ID y el mismo cuerpo | Idempotencia; cambiar el cuerpo con el mismo ID da 422 `COMANDO_REUTILIZADO` |
| P9 | El cuerpo de toda escritura de comanda, caja y salón **incluye los IDs de la ruta** (salvo `local_id`) y las de comanda incluyen **siempre `mesa_id`** | El servidor calcula la huella sobre cuerpo + ruta, y agrupa la cola FIFO por `mesa_id`: mismo orden por mesa en ambos caminos |
| P10 | `pedido.abrir` propone siempre `pedido_id` (ULID) y `pedido.agregar_item` propone siempre `item_id` | Permite seguir trabajando antes de que el pedido exista (contingencia) |
| P11 | Contingencia de la PWA: solo ante 5xx, 429, tiempo agotado (8 s) o error de red; un reintento por la ruta normal (1 s); después, si es comanda, `POST /contingencia/comandas`. Nunca ante 4xx de negocio | `errores.py` y `contingencia/lambda_function.py` |
| P12 | `409 CONFLICTO_CONCURRENCIA` se reintenta **una** vez con el mismo ID tras 300 ms | Es transitorio y no queda guardado en el CMD |
| P13 | Cola local **solo** en un equipo registrado como estación de caja (`ESTACION#`) y con rol dueño, admin o cajero. Solo encola las 7 operaciones de comanda | 01-modelo: «Equipos registrados como PC de caja (habilita la cola local)»; el drenador solo reaplica esas 7 |
| P14 | Al volver internet, la cola local se envía **por `POST /contingencia/comandas`**, en orden, de a uno. **Esto corrige el texto de S9 en 05** («por la ruta normal») | Así las impresiones quedan retenidas (la cocina ya atendió en papel) y los rechazos llegan a la bandeja de conflictos del servidor y al correo del dueño. Por la ruta normal se imprimiría todo de nuevo y los rechazos solo quedarían en ese equipo |
| P15 | Una mesa con comandos aceptados en contingencia queda **«sincronizando»** hasta que el pedido del servidor los refleje, aparezca su conflicto o pasen 120 s. Mientras tanto, sus comandas también van por contingencia | Evita que un comando nuevo adelante a los encolados |
| P16 | IndexedDB (`pos-caja`) solo en la estación: cola, rechazados, caché de plano, carta, pedidos vistos y la «sesión de estación» (sin token). Los celulares no guardan nada | 00-inventario §7 |
| P17 | Si la estación se recarga sin internet, entra en «modo sin conexión» con la última sesión guardada (máx. 12 h): solo salón y comanda. Para enviar la cola hay que ingresar con Google cuando vuelva internet | El token no se guarda (P5) |
| P18 | Sondeos: plano `?solo_estado=1` cada 10 s, pedido abierto cada 15 s, carta con `?version=` al entrar y cada 5 min, documento tributario cada 3 s (máx. 60 s). Solo con la pestaña visible y en línea | D20 de caracterización; costo bajo |
| P19 | Al entrar a una mesa libre se ejecuta `pedido.abrir`, igual que el POS anterior | Comportamiento conservado |
| P20 | Asignar garzón solo para dueño y admin (necesita `GET /admin/personal`, que el cajero no puede leer) | No hay ruta de personal para cajero; no se agregan rutas |
| P21 | Fuera de alcance: reservas, pedidos externos, pantalla de cocina (rol `cocina`), imagen de producto, impresión de precuenta, enrolamiento de nodo/nube, imagen de fondo del login (2,6 MB) | Sin ruta en el backend o fuera del alcance de la v2 |
| P22 | Service worker propio (`public/sw.js`) con lista de precarga generada en la compilación; aviso «Hay una versión nueva» | 04 C3 |
| P23 | Servidor de desarrollo de Vite en `http://localhost:8000` (`strictPort`) | Es el origen permitido por CORS en la API real y en Google |

---

## 3. Contrato con las Lambdas

Base: `config().api_url`. Toda ruta privada lleva `Authorization: Bearer <ID token>`. Toda escritura
lleva `X-Command-Id: <ULID>` y `Content-Type: application/json`. CORS permite solo los encabezados
`authorization`, `content-type` y `x-command-id`; no envíes otros. La respuesta puede traer
`x-comando-repetido: true` (comando ya aplicado antes; se trata igual que un éxito).

ULID válido: `^[0-7][0-9A-HJKMNP-TV-Z]{25}$`. IDs de entidades del seed (`m01`, `local_01`...) no son
ULID: no los valides en el cliente.

### 3.1 Errores

Cuerpo de error de las Lambdas: `{"codigo", "mensaje", "requestId", "detalle"?}`. El API Gateway
responde por su cuenta `401 {"message":"Unauthorized"}` (token ausente o inválido),
`429 {"message":"Too Many Requests"}`, y 500 o 503 con `{"message": ...}` si la función falla o tarda.

| HTTP | Qué hace la PWA |
|---|---|
| 400, 404, 409 (salvo `CONFLICTO_CONCURRENCIA`), 422, 403 | Rechazo de negocio: muestra `mensaje`. Con `codigo = CAMPO_INVALIDO`, marca el campo `detalle.campo` |
| 409 `CONFLICTO_CONCURRENCIA` | Reintenta una vez (P12); si vuelve, muestra el mensaje |
| 401 | Sesión vencida: guarda el comando en memoria, muestra «Ingresar», y al volver a ingresar lo reintenta **con el mismo ID** |
| 403 `USUARIO_NO_REGISTRADO`, `USUARIO_ARCHIVADO`, `EMAIL_NO_VERIFICADO` (en `/yo`) | Pantalla «Sin acceso» con el mensaje y botón «Usar otra cuenta» |
| 429, 5xx, tiempo agotado, error de red | Falla de servicio: reintento y contingencia (P11) |

Códigos que la interfaz debe reconocer para guiar al usuario (además de mostrar el mensaje):
`PEDIDO_EN_PRECUENTA` (ofrecer «Reabrir»), `CONFIRMACION_REQUERIDA`, `ITEM_YA_ENVIADO`,
`MESA_BLOQUEADA`, `MESA_CON_PEDIDO`, `TURNO_NO_ABIERTO` (llevar a la pestaña Turno),
`TURNO_YA_ABIERTO`, `CONTEO_YA_REGISTRADO`, `FALTA_CONTEO`, `FALTA_SEGUNDO_CONTEO`,
`FALTA_CONCILIACION`, `MONTO_EXCEDE_SALDO` (`detalle.saldo`), `MONTO_NO_CORRESPONDE`
(`detalle.esperado`), `EFECTIVO_INSUFICIENTE`, `CODIGO_POS_REQUERIDO`, `ITEM_SIN_UNIDADES`,
`SALDO_PENDIENTE`, `RUT_INVALIDO`, `RAZON_SOCIAL_INVALIDA`, `CODIGO_AUTORIZACION_INVALIDO`
(`detalle.intentos_restantes`), `AUTORIZACION_BLOQUEADA` (`detalle.minutos`), `AUTORIZADOR_INVALIDO`,
`DOCUMENTO_NO_EMITIDO`, `SIN_IMPRESORA_DE_CAJA`, `CAMBIO_PROPIO`, `YA_ES_MIEMBRO`,
`INVITACION_EXISTENTE`, `DUPLICADO`, `ROL_NO_PERMITIDO`, `SIN_ACCESO_AL_LOCAL`.

### 3.2 Tipos de respuesta (copiar a `pwa/src/api/tipos.ts`)

```ts
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
```

### 3.3 Rutas que usa la PWA (cuerpo exacto y respuesta)

`L` = `/locales/{local_id}`. «Cuerpo» es exactamente lo que se envía (claves opcionales: se omiten si
no hay valor; nunca se envía `null` salvo donde se indica).

**Salón y comanda**

| Ruta | Cuerpo | Respuesta |
|---|---|---|
| `GET /salud` (pública) | — | `200 {estado:"ok", ...}`; `503` si DynamoDB no responde |
| `GET /yo` | — | `200 Yo` |
| `GET L/salon` · `?solo_estado=1` | — | `200 Plano` · `200 {mesas: EstadoMesaSolo[]}` |
| `GET L/catalogo` · `?version=N` | — | `200 Carta` · `200 {version, sin_cambios: true}` |
| `POST L/mesas/{mesa_id}/bloqueo` | `{mesa_id, bloqueada: boolean}` | `200 EstadoMesaSolo` |
| `POST L/mesas/{mesa_id}/garzon` | `{mesa_id, garzon_id: string \| null}` | `200 EstadoMesaSolo` |
| `GET L/pedidos/{pedido_id}` | — | `200 Pedido` |
| `POST L/pedidos` — **pedido.abrir** | `{mesa_id, pedido_id}` | `201 Pedido` (o `200` con el pedido que ya tenía la mesa: usa ese `pedido_id`) |
| `POST L/pedidos/{p}/items` — **pedido.agregar_item** | `{pedido_id, mesa_id, item_id, producto_id, cantidad, modificador_id?, observacion?}` | `201 Item` |
| `PATCH L/pedidos/{p}/items/{i}` — **pedido.modificar_item** | `{pedido_id, item_id, mesa_id, cantidad?, observacion?}` (`observacion: ""` la borra) | `200 Item` |
| `DELETE L/pedidos/{p}/items/{i}` — **pedido.quitar_item** | `{pedido_id, item_id, mesa_id}` | `200 {pedido_id, item_id, eliminado: true}` |
| `POST L/pedidos/{p}/enviar` — **pedido.enviar_tanda** | `{pedido_id, mesa_id}` | `200 {tanda: number \| null, items: Item[], impresion: Impresion[]}` |
| `POST L/pedidos/{p}/precuenta` — **pedido.precuenta** | `{pedido_id, mesa_id}` | `200 {pedido: Pedido, items_en_espera: number}` |
| `POST L/pedidos/{p}/reabrir` — **pedido.reabrir** | `{pedido_id, mesa_id, confirmado: true}` | `200 {pedido: Pedido}` |
| Cualquiera de las 7 de comanda, en contingencia del servidor | igual | `202 {estado: "aceptada_en_contingencia", command_id}` |
| `POST /contingencia/comandas` | `{operacion, local_id, cuerpo, ocurrido_en}` (`cuerpo` = el cuerpo exacto de la operación; `ocurrido_en` = ISO de cuando el usuario actuó) | `202 {estado: "aceptada_en_contingencia", command_id}` |

`operacion` ∈ `pedido.abrir`, `pedido.agregar_item`, `pedido.modificar_item`, `pedido.quitar_item`,
`pedido.enviar_tanda`, `pedido.precuenta`, `pedido.reabrir`.

**Caja** (dueño, admin, cajero)

| Ruta | Cuerpo | Respuesta |
|---|---|---|
| `GET L/caja/turno` | — | `200 Turno`; `404 TURNO_NO_ABIERTO` = sin turno (no es error) |
| `POST L/caja/turnos` | `{monto_apertura}` | `201 Turno` |
| `POST L/caja/turnos/{t}/conteo` | `{turno_id, monto}` | `200 {turno, requiere_segundo_conteo, conteo_completado}` (arqueo ciego: no trae el esperado) |
| `POST L/caja/turnos/{t}/conciliacion` | `{turno_id, total_debito_pos, total_credito_pos, total_notas_credito_pos}` | `200 {turno}` |
| `POST L/caja/turnos/{t}/cerrar` | `{turno_id}` | `200 {turno, ...ResultadoCierre}` |
| `GET L/caja/pendientes` | — | `200 {pendientes: {mesa_id, pedido: Pedido}[]}` |
| `POST L/pedidos/{p}/pagos` | `{pedido_id, medios: Medio[1..2], tipo_division, items_cobrados?}` | `201 {pagos: Pago[], pedido: {pedido_id, total, pagado, saldo, propina_total}}` |
| `POST L/pedidos/{p}/finalizar` | `{pedido_id, tipo_documento, receptor?}`; si `total = 0`, solo `{pedido_id}` | `200 {pedido, documento: {tipo, estado:"pendiente"} \| null}` |
| `GET L/caja/documentos` · `?turno_id=` | — | `200 {turno_id, documentos: Documento[]}` |
| `GET L/caja/documentos/{venta_id}` | — | `200 Documento` (`venta_id` = `pedido_id`) |
| `POST L/caja/documentos/{v}/reimprimir` | `{venta_id}` | `200 {venta_id, trabajo_id, estado:"encolada"}` |
| `GET L/caja/autorizadores` | — | `200 {autorizadores: Autorizador[]}` |
| `GET L/caja/retiros` · `?turno_id=` | — | `200 {turno_id, retiros: Retiro[]}` |
| `POST L/caja/retiros` | `{monto, motivo, autorizador_id, codigo}` | `201 Retiro` |
| `GET L/caja/conflictos` · `?todos=1` | — | `200 {conflictos: Conflicto[]}` (por defecto solo abiertos) |
| `POST L/caja/conflictos/{c}/resolver` | `{conflicto_id, resolucion: "resuelto" \| "descartado", nota?}` | `200 Conflicto` |
| `GET L/caja/impresiones-retenidas` | — | `200 {trabajos: TrabajoRetenido[]}` |
| `POST L/caja/impresiones-retenidas/{t}/liberar` | `{trabajo_id}` | `200 {trabajo_id, estado:"encolada"}` |
| `POST L/caja/impresiones-retenidas/{t}/descartar` | `{trabajo_id}` | `200 {trabajo_id, estado:"descartado"}` |

`Medio` = `{metodo, monto, propina?}` más: `codigo_autorizacion_pos` (obligatorio en débito y crédito)
o `efectivo_recibido` (obligatorio en efectivo, ≥ monto + propina). `items_cobrados` =
`[{item_id, cantidad}]`, solo con `tipo_division = "items"`. `receptor` = `{rut, razon_social}`, solo
con factura. Factura: RUT sin puntos ni espacios, en mayúsculas, que cumpla `^\d{7,8}-[\dK]$`; razón
social de 2 a 200 caracteres.

**Administración** (dueño y admin; `recurso` en la ruta). Los cuerpos de administración llevan solo
los campos: el servidor pone el ID de la ruta.

| Recurso | `GET L/admin/{recurso}` | `POST L/admin/{recurso}` (crear) | `PATCH L/admin/{recurso}/{id}` (editar) | Otros |
|---|---|---|---|---|
| `sectores` | `{sectores: Sector[]}` | `{nombre, activo?}` | `{nombre?, activo?}` | — |
| `mesas` | `{mesas: [{mesa_id, sector_id, sector_nombre, numero, capacidad, activa}]}` | `{sector_id, numero, capacidad?}` | `{numero?, capacidad?, sector_id?, activa?}` | — |
| `productos` | `{productos: Producto[]}` | `{nombre, categoria, precio, cuarto_id, activo?, descripcion?, modificadores?: [{nombre, precio_adicional?}]}` | igual, todo opcional; en `modificadores` (lista completa) los existentes llevan su `modificador_id` | — |
| `cuartos` | `{cuartos: [{cuarto_id, nombre, descripcion, activo, impresora_id?}]}` | `{nombre, descripcion?, activo?, impresora_id?}` | igual, opcional; `impresora_id: null` la quita | — |
| `impresoras` | `{impresoras: [{impresora_id, nombre, modelo, protocolo, activa}]}` | `{nombre, modelo?, activa?}` → `201 {..., clave, usuario_cloudprnt}` | `{nombre?, modelo?, activa?}` | `POST L/admin/impresoras/{id}/rotar-clave` `{}` → `{..., clave, usuario_cloudprnt}` |
| `materias-primas` | `{"materias-primas": [{materia_prima_id, nombre, unidad, stock_actual_mil, stock_minimo_mil, activo}]}` | `{nombre, unidad, stock_actual?, stock_minimo?, activo?}` (decimales, hasta 3) | igual, opcional | — |
| `recetas` | `{recetas: [{producto_id, ingredientes: [{materia_prima_id, cantidad_mil}]}]}` | — | `PATCH L/admin/recetas/{producto_id}` `{ingredientes: [{materia_prima_id, cantidad}]}` (1 a 50, sin repetir, cantidad > 0) | — |
| `configuracion` | objeto local: `{nombre_local, marca, propina_sugerida_pct, umbral_diferencia_pb, umbral_diferencia_pct, umbral_diferencia_minimo, impresora_caja_id?}` | — | `PATCH L/admin/configuracion/local` `{nombre_local?, marca?, propina_sugerida_pct?, umbral_diferencia_pct?, umbral_diferencia_minimo?, impresora_caja_id? (null la quita)}` | — |
| `personal` | `{personal: [{sub \| null, nombre, email, rol, estado, invitacion: boolean}]}` | `{email, nombre, rol}` (admin no puede dar `dueno`) | `PATCH L/admin/personal/{sub}` `{rol?, estado?: "activo" \| "archivado", nombre?}` | — |
| `invitaciones` | — | — | — | `DELETE L/admin/invitaciones/{email}` `{}` |
| `mi-codigo` | — | `POST L/admin/mi-codigo` `{codigo}` (4 a 8 dígitos) → `{actualizado: true}` | — | — |
| `estaciones` | `{estaciones: [{estacion_id, nombre, tipo, creada_por, creada_en}]}` | `{nombre}` | — | `DELETE L/admin/estaciones/{id}` `{}` |

El email en `DELETE .../invitaciones/{email}` va como `encodeURIComponent(email).replace(/%40/g, "@")`.
No existen borrados de productos, mesas, sectores, cuartos, impresoras ni personas: se desactivan
(`activo`/`activa: false`) o se archivan (`estado: "archivado"`).

**Reportes** (dueño y admin)

| Ruta | Respuesta |
|---|---|
| `GET L/reportes/turnos?desde=AAAA-MM-DD&hasta=AAAA-MM-DD` | `{turnos: [{turno_id, fecha_operativa, estado, abierto_en, cerrado_en?, diferencia_efectivo?, total_ventas?}]}` |
| `GET L/reportes/turnos/{turno_id}` | `{turno: {...Turno, efectivo_esperado}, caja: {efectivo, debito, credito, transferencia, retiros, n_pagos, n_ventas, total_ventas}, resumen: {n_ventas?, total_ventas?, total_propinas?, n_retiros?, total_retiros?}, por_garzon: [{garzon_id, n_ventas, total_ventas, total_propinas}], retiros: Retiro[], documentos: {[estado]: number}}` |
| `GET L/reportes/dias/{fecha}` | `{fecha, resumen: {n_ventas?, total_ventas?, total_propinas?, n_cerrados_sin_venta?}}` |

**Rutas que la PWA NO usa:** `/impresion/*` (impresoras), `/publico/*` (reservas), `/webhooks/*`.

### 3.4 Matriz de rol por pantalla (`roles.py`)

| Pantalla | dueño | admin | cajero | garzón | cocina |
|---|---|---|---|---|---|
| Salón y comanda | ✔ | ✔ | ✔ | ✔ | — |
| Bloquear o desbloquear mesa | ✔ | ✔ | ✔ | — | — |
| Asignar garzón (P20) | ✔ | ✔ | — | — | — |
| Caja (todas sus pestañas) | ✔ | ✔ | ✔ | — | — |
| Administración y reportes | ✔ | ✔ | — | — | — |
| Dar o cambiar el rol dueño | ✔ | — | — | — | — |
| Mi código de autorización | ✔ | ✔ | — | — | — |
| Inicio por defecto | Administración | Administración | Caja | Salón | «Tu rol no tiene pantalla en la PWA» |

---

## 4. Estructura de `pwa/`

```
pwa/
  package.json  vite.config.ts  vitest.config.ts  tsconfig.json  tsconfig.app.json  tsconfig.node.json
  eslint.config.js  components.json  index.html  config.example.json  README.md
  public/
    sw.js  manifest.webmanifest  favicon.svg  icons.svg  mise-logo.png
    config.json            <- NO se versiona (copia de config.example.json)
  src/
    main.tsx  App.tsx  index.css  gis.d.ts  config.ts
    lib/        utils.ts  ulid.ts  dinero.ts  fechas.ts  rut.ts
    api/        tipos.ts  cliente.ts  comandos.ts  rutas.ts  salon.ts  pedidos.ts  caja.ts  admin.ts  reportes.ts
    sesion/     google.ts  SesionProvider.tsx  useSesion.ts  RequiereRol.tsx
    offline/    db.ts  cola.ts  red.ts  estacion.ts  sincronizar.ts  pedidoLocal.ts  cache.ts
    pwa/        registrarServiceWorker.ts
    hooks/      useSondeo.ts  useEnLinea.ts
    components/ ui/ (button, dialog)  comun/ (Aviso, Notificaciones, BarraConexion, SelectorLocal)
                pos/  caja/  dashboard/
    layouts/    AdminLayout.tsx  LayoutOperacion.tsx
    pages/      auth/ (LoginPage, SinAcceso, SinPantalla)  pos/ (TablesPage, OrderPage)
                caja/ (PanelCaja)  dashboard/ (...)  locales/ (SelectorLocalPage)
    test/       setup.ts
```

---

## 5. Código base (copiar tal cual)

Estos módulos son la parte delicada. Cópialos exactamente; solo ajusta importaciones si TypeScript lo
exige.

### 5.1 `src/config.ts`

```ts
export interface Config {
  api_url: string
  google_client_id: string
  modo_dev: boolean
}

let actual: Config | null = null

export async function cargarConfig(): Promise<Config> {
  const respuesta = await fetch("./config.json", { cache: "no-store" })
  if (!respuesta.ok) throw new Error("No se encontró config.json")
  const datos = (await respuesta.json()) as Partial<Config>
  actual = {
    api_url: String(datos.api_url ?? "").replace(/\/+$/, ""),
    google_client_id: String(datos.google_client_id ?? ""),
    modo_dev: datos.modo_dev === true,
  }
  return actual
}

export function config(): Config {
  if (!actual) throw new Error("La configuración no está cargada")
  return actual
}

/** Solo para pruebas. */
export function fijarConfig(valor: Config): void {
  actual = valor
}
```

### 5.2 `src/lib/ulid.ts`

```ts
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
```

### 5.3 `src/lib/dinero.ts` (mismas reglas que `pos_dominio/dinero.py`)

```ts
import type { Item } from "@/api/tipos"

const CLP = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 })
export const pesos = (monto: number): string => CLP.format(monto)

/** round_half_up(monto * pct / 100), igual que el servidor. */
export const propinaSugerida = (monto: number, pct: number): number => Math.floor((monto * pct + 50) / 100)

export function dividirPartesIguales(total: number, personas: number): number[] {
  if (personas < 2 || personas > 20) throw new Error("La cuenta se divide entre 2 y 20 personas")
  if (total < personas) throw new Error("El saldo es menor que la cantidad de personas: alguna parte quedaría en $0")
  const base = Math.floor(total / personas)
  const resto = total % personas
  return Array.from({ length: personas }, (_, i) => base + (i < resto ? 1 : 0))
}

/** mín(Σ precio congelado × cantidad, saldo); suma antes las líneas repetidas del mismo ítem. */
export function montoPorItems(items: Item[], seleccion: { item_id: string; cantidad: number }[], saldo: number): number {
  const agrupado = new Map<string, number>()
  for (const s of seleccion) agrupado.set(s.item_id, (agrupado.get(s.item_id) ?? 0) + s.cantidad)
  let total = 0
  for (const [itemId, cantidad] of agrupado) {
    const item = items.find((i) => i.item_id === itemId)
    if (!item) throw new Error("Uno de los ítems no pertenece a este pedido")
    if (cantidad > item.cantidad - item.cobrado) throw new Error("La cantidad cobrada excede lo disponible para ese ítem")
    total += item.precio_unitario * cantidad
  }
  return Math.min(total, saldo)
}

export const milesimas = (valor: number): string =>
  (valor / 1000).toLocaleString("es-CL", { maximumFractionDigits: 3 })
```

`src/lib/fechas.ts`: `hora(iso)` y `fechaHora(iso)` con `Intl.DateTimeFormat("es-CL", {timeZone: "America/Santiago", ...})`;
`hoySantiago()` con `new Intl.DateTimeFormat("en-CA", {timeZone: "America/Santiago"}).format(new Date())`
(da `AAAA-MM-DD`). `src/lib/rut.ts`: `normalizarRut(t) = t.replace(/[.\s]/g, "").toUpperCase()` y
`rutValido(t) = /^\d{7,8}-[\dK]$/.test(normalizarRut(t))`. `src/lib/utils.ts`: solo `cn` (copiado del
anterior); `generateId` se elimina.

### 5.4 `src/gis.d.ts`

```ts
interface GoogleAccountsId {
  initialize(opciones: Record<string, unknown>): void
  renderButton(elemento: HTMLElement, opciones: Record<string, unknown>): void
  prompt(): void
  disableAutoSelect(): void
}
interface Window {
  google?: { accounts: { id: GoogleAccountsId } }
}
```

### 5.5 `src/sesion/google.ts`

```ts
import { config } from "@/config"

export interface EstadoSesion { token: string | null; expira: number; sub: string; nombre: string; email: string }

const VACIA: EstadoSesion = { token: null, expira: 0, sub: "", nombre: "", email: "" }
let estado: EstadoSesion = VACIA
const oyentes = new Set<() => void>()
let renovacion: number | undefined
let cargando: Promise<void> | null = null

export function suscribirSesion(oyente: () => void): () => void {
  oyentes.add(oyente)
  return () => { oyentes.delete(oyente) }
}
export const estadoSesion = (): EstadoSesion => estado
const emitir = () => oyentes.forEach((o) => o())

/** El token, si le queda más de un minuto. Nunca se guarda fuera de esta variable. */
export function tokenVigente(): string | null {
  return estado.token && Date.now() < estado.expira - 60_000 ? estado.token : null
}

export function sesionVencida(): void {
  estado = { ...estado, token: null, expira: 0 }
  emitir()
}

function leerPayload(jwt: string): Record<string, unknown> {
  const parte = jwt.split(".")[1] ?? ""
  const base64 = parte.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(parte.length / 4) * 4, "=")
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
  return JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>
}

function recibirCredencial(jwt: string): void {
  const p = leerPayload(jwt)
  estado = { token: jwt, expira: Number(p.exp) * 1000, sub: String(p.sub ?? ""), nombre: String(p.name ?? ""), email: String(p.email ?? "") }
  window.clearTimeout(renovacion)
  renovacion = window.setTimeout(() => window.google?.accounts.id.prompt(), Math.max(0, estado.expira - Date.now() - 5 * 60_000))
  emitir()
}

export function cargarGoogle(autoSeleccion: boolean): Promise<void> {
  if (cargando) return cargando
  cargando = new Promise<void>((resolver, rechazar) => {
    const script = document.createElement("script")
    script.src = "https://accounts.google.com/gsi/client"
    script.async = true
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: config().google_client_id,
        callback: (r: { credential: string }) => recibirCredencial(r.credential),
        auto_select: autoSeleccion,
        use_fedcm_for_prompt: true,
        cancel_on_tap_outside: false,
      })
      resolver()
    }
    script.onerror = () => {
      cargando = null
      rechazar(new Error("No se pudo cargar el inicio de sesión de Google"))
    }
    document.head.appendChild(script)
  })
  return cargando
}

export const dibujarBotonGoogle = (elemento: HTMLElement): void =>
  window.google?.accounts.id.renderButton(elemento, { theme: "outline", size: "large", locale: "es", text: "signin_with" })

export const intentarIngresoSilencioso = (): void => window.google?.accounts.id.prompt()

export function ingresarDev(sub: string): void {
  if (!config().modo_dev) throw new Error("El ingreso de desarrollo está desactivado")
  estado = { token: `dev:${sub}`, expira: Date.now() + 12 * 3600_000, sub, nombre: sub, email: `${sub}@demo.invalid` }
  emitir()
}

export function cerrarSesion(): void {
  window.clearTimeout(renovacion)
  window.google?.accounts.id.disableAutoSelect()
  estado = VACIA
  emitir()
}
```

### 5.6 `src/offline/red.ts`

```ts
import { config } from "@/config"

type EstadoRed = "en_linea" | "sin_conexion"
let estado: EstadoRed = navigator.onLine ? "en_linea" : "sin_conexion"
const oyentes = new Set<() => void>()
let sondeo: number | undefined

function cambiar(nuevo: EstadoRed): void {
  if (nuevo === estado) return
  estado = nuevo
  if (nuevo === "sin_conexion" && sondeo === undefined) sondeo = window.setInterval(() => void sondear(), 10_000)
  if (nuevo === "en_linea" && sondeo !== undefined) { window.clearInterval(sondeo); sondeo = undefined }
  oyentes.forEach((o) => o())
}

/** Vuelve "en línea" solo si /salud responde 200 (la API y DynamoDB responden). */
async function sondear(): Promise<void> {
  try {
    const r = await fetch(`${config().api_url}/salud`, { cache: "no-store", signal: AbortSignal.timeout(5000) })
    if (r.status === 200) cambiar("en_linea")
  } catch {
    /* sigue sin conexión */
  }
}

window.addEventListener("offline", () => cambiar("sin_conexion"))
window.addEventListener("online", () => void sondear())

export const red = {
  estado: (): EstadoRed => estado,
  sinConexion: (): boolean => estado === "sin_conexion",
  suscribir(oyente: () => void): () => void {
    oyentes.add(oyente)
    return () => { oyentes.delete(oyente) }
  },
  reportarFalla: (): void => cambiar("sin_conexion"),
  reportarRespuesta: (): void => cambiar("en_linea"),
  sondear,
}
```

### 5.7 `src/api/cliente.ts`

```ts
import { config } from "@/config"
import { red } from "@/offline/red"
import { sesionVencida, tokenVigente } from "@/sesion/google"

export class ErrorApi extends Error {
  readonly http: number
  readonly codigo: string
  readonly detalle: Record<string, unknown>
  readonly requestId: string
  constructor(http: number, codigo: string, mensaje: string, detalle: Record<string, unknown> = {}, requestId = "") {
    super(mensaje)
    this.name = "ErrorApi"
    this.http = http
    this.codigo = codigo
    this.detalle = detalle
    this.requestId = requestId
  }
  get esFallaDeServicio(): boolean {
    return this.http >= 500 || this.http === 429
  }
}

export class SinConexion extends Error {
  constructor(mensaje = "Sin conexión") {
    super(mensaje)
    this.name = "SinConexion"
  }
}

export class SesionRequerida extends Error {
  constructor() {
    super("Ingresa de nuevo para continuar")
    this.name = "SesionRequerida"
  }
}

export type Metodo = "GET" | "POST" | "PATCH" | "DELETE"
export interface Respuesta<T> { http: number; datos: T; repetido: boolean }
interface Opciones {
  cuerpo?: unknown
  commandId?: string
  query?: Record<string, string | undefined>
  publica?: boolean
  timeoutMs?: number
}

export const TIEMPO_MAXIMO_MS = 8000

export async function pedir<T>(metodo: Metodo, ruta: string, op: Opciones = {}): Promise<Respuesta<T>> {
  const token = op.publica ? null : tokenVigente()
  if (!op.publica && !token) throw new SesionRequerida()
  const params = new URLSearchParams()
  for (const [clave, valor] of Object.entries(op.query ?? {})) if (valor !== undefined) params.set(clave, valor)
  const qs = params.toString()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (op.commandId) headers["X-Command-Id"] = op.commandId
  if (op.cuerpo !== undefined) headers["Content-Type"] = "application/json"

  const control = new AbortController()
  const temporizador = window.setTimeout(() => control.abort(), op.timeoutMs ?? TIEMPO_MAXIMO_MS)
  let r: Response
  try {
    r = await fetch(`${config().api_url}${ruta}${qs ? `?${qs}` : ""}`, {
      method: metodo,
      headers,
      body: op.cuerpo === undefined ? undefined : JSON.stringify(op.cuerpo),
      signal: control.signal,
      cache: "no-store",
    })
  } catch {
    red.reportarFalla()
    throw new SinConexion()
  } finally {
    window.clearTimeout(temporizador)
  }
  red.reportarRespuesta()

  const esJson = (r.headers.get("content-type") ?? "").includes("application/json")
  const datos: unknown = esJson ? await r.json().catch(() => ({})) : await r.text()
  if (r.status === 401) {
    sesionVencida()
    throw new SesionRequerida()
  }
  if (!r.ok) {
    const d = (typeof datos === "object" && datos !== null ? datos : {}) as Record<string, unknown>
    const generico = r.status >= 500 || r.status === 429
      ? "El servicio no está disponible en este momento. Intenta de nuevo."
      : "No se pudo completar la acción."
    throw new ErrorApi(r.status, String(d.codigo ?? `HTTP_${r.status}`), String(d.mensaje ?? generico),
      (d.detalle as Record<string, unknown> | undefined) ?? {}, String(d.requestId ?? ""))
  }
  return { http: r.status, datos: datos as T, repetido: r.headers.get("x-comando-repetido") === "true" }
}

export async function leer<T>(ruta: string, query?: Record<string, string | undefined>): Promise<T> {
  return (await pedir<T>("GET", ruta, { query })).datos
}
```

### 5.8 `src/api/comandos.ts`

```ts
import { ErrorApi, pedir, SinConexion, type Respuesta } from "@/api/cliente"
import type { Item } from "@/api/tipos"
import { ulid } from "@/lib/ulid"
import { cola } from "@/offline/cola"
import { estacionActiva } from "@/offline/estacion"
import { red } from "@/offline/red"
import { sincronizacion } from "@/offline/sincronizar"

export const OPERACIONES_COMANDA = [
  "pedido.abrir", "pedido.agregar_item", "pedido.modificar_item", "pedido.quitar_item",
  "pedido.enviar_tanda", "pedido.precuenta", "pedido.reabrir",
] as const
export type OperacionComanda = (typeof OPERACIONES_COMANDA)[number]

/** Datos para mostrar un ítem agregado antes de que el servidor responda. No se envían. */
export type VistaItem = Pick<Item, "nombre" | "categoria" | "cuarto_id" | "precio_unitario" | "modificador_nombre">

export interface Comando {
  readonly id: string
  readonly localId: string
  readonly metodo: "POST" | "PATCH" | "DELETE"
  readonly ruta: string
  readonly cuerpo: Readonly<Record<string, unknown>>
  readonly operacion: OperacionComanda | null
  readonly mesaId: string | null
  readonly creadoEn: string
  readonly vistaItem?: VistaItem
}

export function crearComando(
  localId: string, metodo: Comando["metodo"], ruta: string, cuerpo: Record<string, unknown>,
  operacion: OperacionComanda | null = null, vistaItem?: VistaItem,
): Comando {
  const limpio = Object.fromEntries(Object.entries(cuerpo).filter(([, v]) => v !== undefined))
  return Object.freeze({
    id: ulid(), localId, metodo, ruta, cuerpo: Object.freeze(limpio), operacion,
    mesaId: typeof limpio.mesa_id === "string" ? limpio.mesa_id : null,
    creadoEn: new Date().toISOString(), vistaItem,
  })
}

export type Resultado<T> =
  | { via: "normal"; respuesta: Respuesta<T> }
  | { via: "contingencia" }
  | { via: "cola_local" }

const esperar = (ms: number) => new Promise((r) => window.setTimeout(r, ms))
const esFalla = (e: unknown): boolean => e instanceof SinConexion || (e instanceof ErrorApi && e.esFallaDeServicio)

export async function ejecutar<T>(c: Comando): Promise<Resultado<T>> {
  const comanda = c.operacion !== null
  const estacion = comanda && estacionActiva(c.localId) !== null
  // Sin conexión, o con comandas ya guardadas, la estación sigue guardando en orden.
  if (estacion && (red.sinConexion() || (await cola.contar(c.localId)) > 0)) {
    await cola.agregar(c)
    return { via: "cola_local" }
  }
  if (comanda && c.mesaId && sincronizacion.activa(c.localId, c.mesaId)) return porContingencia<T>(c)

  let ultimo: unknown = null
  for (let intento = 0; intento < 2; intento++) {
    try {
      const respuesta = await pedir<T>(c.metodo, c.ruta, { cuerpo: c.cuerpo, commandId: c.id })
      if (respuesta.http === 202) {
        sincronizacion.registrar(c)
        return { via: "contingencia" }
      }
      return { via: "normal", respuesta }
    } catch (e) {
      if (e instanceof ErrorApi && e.codigo === "CONFLICTO_CONCURRENCIA" && intento === 0) {
        await esperar(300)
        continue
      }
      if (!esFalla(e)) throw e
      ultimo = e
      if (e instanceof SinConexion && !navigator.onLine) break
      if (intento === 0) await esperar(1000)
    }
  }
  if (!comanda) throw ultimo instanceof SinConexion ? new SinConexion("Sin conexión: esta acción necesita internet") : ultimo
  return porContingencia<T>(c)
}

async function porContingencia<T>(c: Comando): Promise<Resultado<T>> {
  try {
    await pedir("POST", "/contingencia/comandas", {
      cuerpo: { operacion: c.operacion, local_id: c.localId, cuerpo: c.cuerpo, ocurrido_en: c.creadoEn },
      commandId: c.id,
    })
    sincronizacion.registrar(c)
    return { via: "contingencia" }
  } catch (e) {
    if (!esFalla(e)) throw e
    if (estacionActiva(c.localId) !== null) {
      await cola.agregar(c)
      return { via: "cola_local" }
    }
    throw new SinConexion("Sin conexión: usa la caja")
  }
}
```

Si `ejecutar` lanza `SesionRequerida`, la pantalla conserva el **mismo** objeto `Comando`, muestra
«Ingresar» y, al volver la sesión, llama otra vez a `ejecutar(c)`.

### 5.9 `src/offline/db.ts`, `cola.ts`, `cache.ts`, `estacion.ts`

```ts
// db.ts
import { openDB, type DBSchema, type IDBPDatabase } from "idb"
import type { Comando } from "@/api/comandos"

export interface Guardado extends Comando { seq?: number; registradoPor: { sub: string; nombre: string } }
export interface Rechazado extends Guardado { codigo: string; mensaje: string; rechazadoEn: string }
export interface EntradaCache { clave: string; valor: unknown; guardadoEn: number }

interface EsquemaPos extends DBSchema {
  comandos: { key: number; value: Guardado; indexes: { porLocal: string; porId: string } }
  rechazados: { key: string; value: Rechazado }
  cache: { key: string; value: EntradaCache }
}

let conexion: Promise<IDBPDatabase<EsquemaPos>> | null = null
export function db(): Promise<IDBPDatabase<EsquemaPos>> {
  conexion ??= openDB<EsquemaPos>("pos-caja", 1, {
    upgrade(base) {
      const comandos = base.createObjectStore("comandos", { keyPath: "seq", autoIncrement: true })
      comandos.createIndex("porLocal", "localId")
      comandos.createIndex("porId", "id", { unique: true })
      base.createObjectStore("rechazados", { keyPath: "id" })
      base.createObjectStore("cache", { keyPath: "clave" })
    },
  })
  return conexion
}
```

```ts
// cola.ts
import type { Comando } from "@/api/comandos"
import { db, type Guardado, type Rechazado } from "@/offline/db"
import { estadoSesion } from "@/sesion/google"
import { sesionDeEstacion } from "@/offline/estacion"

const oyentes = new Set<() => void>()
const avisar = () => oyentes.forEach((o) => o())

export const cola = {
  suscribir(oyente: () => void): () => void {
    oyentes.add(oyente)
    return () => { oyentes.delete(oyente) }
  },
  async agregar(c: Comando): Promise<void> {
    const sesion = estadoSesion()
    const respaldo = await sesionDeEstacion(c.localId)
    const registradoPor = sesion.sub ? { sub: sesion.sub, nombre: sesion.nombre } : { sub: respaldo?.sub ?? "", nombre: respaldo?.nombre ?? "" }
    try {
      await (await db()).add("comandos", { ...c, registradoPor })
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "ConstraintError")) throw e // mismo ID: ya estaba en la cola
    }
    avisar()
  },
  async pendientes(localId: string): Promise<Guardado[]> {
    const todos = await (await db()).getAllFromIndex("comandos", "porLocal", localId)
    return todos.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0))
  },
  async contar(localId: string): Promise<number> {
    return (await db()).countFromIndex("comandos", "porLocal", localId)
  },
  async quitar(seq: number): Promise<void> {
    await (await db()).delete("comandos", seq)
    avisar()
  },
  async rechazar(g: Guardado, codigo: string, mensaje: string): Promise<void> {
    const base = await db()
    const registro: Rechazado = { ...g, codigo, mensaje, rechazadoEn: new Date().toISOString() }
    delete registro.seq
    await base.put("rechazados", registro)
    if (g.seq !== undefined) await base.delete("comandos", g.seq)
    avisar()
  },
  async rechazados(localId: string): Promise<Rechazado[]> {
    return (await (await db()).getAll("rechazados")).filter((r) => r.localId === localId)
  },
  async descartarRechazado(id: string): Promise<void> {
    await (await db()).delete("rechazados", id)
    avisar()
  },
}
```

`cache.ts`: `guardarCache(clave, valor)` y `leerCache<T>(clave, maxEdadMs?)` sobre el almacén `cache`
(`guardadoEn = Date.now()`). Claves: `plano:<local>`, `carta:<local>`, `pedido:<local>:<pedido_id>`,
`sesion_estacion:<local>`. **Solo se escribe si `estacionActiva(local)`**.

`estacion.ts`:
- `estacionActiva(localId): string | null` → `localStorage.getItem("pos.estacion." + localId)` dentro
  de `try/catch` (null si falla).
- `activarEstacion(localId, estacionId)` → guarda en `localStorage` y llama a `guardarSesionDeEstacion`.
- `desactivarEstacion(localId)` → solo si `cola.contar(localId) === 0`; si no, lanza
  `Error("Envía o descarta las comandas guardadas antes de desactivar la estación")`.
- `guardarSesionDeEstacion(localId, local: LocalDeUsuario, sub, nombre)` → `cache` clave
  `sesion_estacion:<local>` = `{local, sub, nombre}`. Se llama después de cada `GET /yo` exitoso en la
  estación.
- `sesionDeEstacion(localId)` → la lee si tiene menos de 12 h; si no, `null`.

### 5.10 `src/offline/pedidoLocal.ts`

Reproduce las reglas de `operaciones/pedidos.py` para mostrar el efecto de comandos todavía no
confirmados. Dos modos:
- `"validar"`: lanza `ErrorApi(409 | 404 | 422, codigo, mensaje)` con **los mismos códigos y
  mensajes que el servidor** (abajo). Se usa antes de guardar un comando en la cola local.
- `"superponer"`: nunca lanza; si la regla no se cumple o el comando ya está reflejado, devuelve el
  pedido sin cambios. Se usa para pintar comandos pendientes encima del pedido del servidor.

Firma: `aplicar(pedido: Pedido | null, c: Comando, modo: "validar" | "superponer"): Pedido | null`.
Recalcula siempre `total = Σ subtotal`, `saldo = total - pagado`.

| Operación | Efecto | Reglas (código: mensaje) |
|---|---|---|
| `pedido.abrir` | Si `pedido` existe y no está `cerrado`: sin cambios. Si no: pedido nuevo `{pedido_id, mesa_id, estado:"abierto", items:[], pagos:[], total:0, pagado:0, saldo:0, propina_total:0, n_tandas:0, garzon_id: <sub>, documento:null, creado_en: c.creadoEn, cerrado_en:null}` | — |
| `pedido.agregar_item` | Si ya existe `item_id`: sin cambios. Si no: ítem con `c.vistaItem`, `cantidad`, `cobrado:0`, `subtotal = precio_unitario × cantidad`, `estado:"en_espera"`, `tanda:null`, `observacion`, `creado_en: c.creadoEn` | sin pedido → `PEDIDO_NO_ENCONTRADO: Pedido no encontrado`; precuenta → `PEDIDO_EN_PRECUENTA: La mesa está en precuenta. Reábrela para modificar la comanda.`; cerrado → `PEDIDO_CERRADO: El pedido ya está cerrado` |
| `pedido.modificar_item` | Pone `cantidad` y/o `observacion` (`""` → `null`) | sin ítem → `ITEM_NO_ENCONTRADO: Item no encontrado`; enviado → `ITEM_YA_ENVIADO: El ítem ya fue enviado a cocina y no se puede modificar`; más las de estado de agregar |
| `pedido.quitar_item` | Quita el ítem (si no está: sin cambios) | igual que modificar |
| `pedido.enviar_tanda` | Todos los `en_espera` → `enviado`, `tanda = n_tandas + 1`, `enviado_en = c.creadoEn`; `n_tandas + 1`. Sin ítems en espera: sin cambios | estado como agregar |
| `pedido.precuenta` | `estado = "precuenta"` (si ya lo está: sin cambios) | cerrado → `PEDIDO_CERRADO`; sin ítems → `PEDIDO_VACIO: La mesa no tiene consumo` |
| `pedido.reabrir` | `estado = "abierto"` (si ya lo está: sin cambios) | cerrado → `PEDIDO_CERRADO`; sin `confirmado: true` → `CONFIRMACION_REQUERIDA: Reabrir la mesa deja sin efecto la precuenta. Confirma para continuar.` |

También exporta:
- `huella(p: Pedido | null): string` =
  `p === null ? "null" : JSON.stringify([p.estado, [...p.items].sort(porId).map(i => [i.item_id, i.cantidad, i.observacion ?? null, i.estado])])`.
- `estadoMesa(mesa: MesaPlano, comandos: Comando[]): MesaPlano`: `abrir` → `ocupada` con su
  `pedido_id`; `precuenta` → `precuenta`; `reabrir` → `ocupada`.

### 5.11 `src/offline/sincronizar.ts`

```ts
import { ErrorApi, leer, pedir, SesionRequerida, SinConexion } from "@/api/cliente"
import type { Comando } from "@/api/comandos"
import type { Conflicto, Pedido } from "@/api/tipos"
import { cola } from "@/offline/cola"
import { aplicar, huella } from "@/offline/pedidoLocal"
import { tokenVigente } from "@/sesion/google"

interface Registro { localId: string; mesaId: string; pedidoId: string | null; comandos: Comando[]; desde: number }
const registros = new Map<string, Registro>()
const oyentes = new Set<() => void>()
const avisar = () => oyentes.forEach((o) => o())
const clave = (localId: string, mesaId: string) => `${localId}#${mesaId}`
export const ESPERA_MAXIMA_MS = 120_000

export const sincronizacion = {
  suscribir(oyente: () => void): () => void {
    oyentes.add(oyente)
    return () => { oyentes.delete(oyente) }
  },
  activa: (localId: string, mesaId: string): boolean => registros.has(clave(localId, mesaId)),
  comandos: (localId: string, mesaId: string): Comando[] => registros.get(clave(localId, mesaId))?.comandos ?? [],
  registrar(c: Comando): void {
    if (!c.mesaId) return
    const k = clave(c.localId, c.mesaId)
    const r = registros.get(k) ?? { localId: c.localId, mesaId: c.mesaId, pedidoId: null, comandos: [], desde: Date.now() }
    if (!r.comandos.some((x) => x.id === c.id)) r.comandos.push(c)
    r.pedidoId = typeof c.cuerpo.pedido_id === "string" ? c.cuerpo.pedido_id : r.pedidoId
    registros.set(k, r)
    avisar()
  },
  /** Una pasada: se llama cada 3 s mientras haya registros (ver useSondeo en LayoutOperacion). */
  async verificar(alAvisar: (mensaje: string) => void): Promise<void> {
    const porLocal = new Set([...registros.values()].map((r) => r.localId))
    for (const localId of porLocal) {
      let conflictos: Conflicto[] = []
      try {
        conflictos = (await leer<{ conflictos: Conflicto[] }>(`/locales/${localId}/caja/conflictos`)).conflictos
      } catch {
        /* garzón sin permiso de caja, o sin conexión: se decide solo con el pedido */
      }
      const rechazados = new Set(conflictos.map((x) => x.comando.command_id))
      for (const [k, r] of registros) {
        if (r.localId !== localId) continue
        r.comandos = r.comandos.filter((c) => !rechazados.has(c.id))
        let servidor: Pedido | null = null
        if (r.pedidoId) {
          try {
            servidor = await leer<Pedido>(`/locales/${localId}/pedidos/${r.pedidoId}`)
          } catch (e) {
            if (!(e instanceof ErrorApi && e.http === 404)) continue
          }
        }
        const superpuesto = r.comandos.reduce<Pedido | null>((p, c) => aplicar(p, c, "superponer"), servidor)
        if (r.comandos.length === 0 || huella(superpuesto) === huella(servidor)) {
          registros.delete(k)
        } else if (Date.now() - r.desde > ESPERA_MAXIMA_MS) {
          registros.delete(k)
          alAvisar(`La mesa ${r.mesaId} sigue sincronizando. Revisa la bandeja de conflictos.`)
        }
      }
    }
    avisar()
  },
}

let vaciando = false

/** Envía la cola local por contingencia, en orden. Devuelve cuántos se enviaron. */
export async function vaciarCola(localId: string): Promise<number> {
  if (vaciando || !tokenVigente()) return 0
  vaciando = true
  let enviados = 0
  try {
    for (const g of await cola.pendientes(localId)) {
      try {
        await pedir("POST", "/contingencia/comandas", {
          cuerpo: { operacion: g.operacion, local_id: g.localId, cuerpo: g.cuerpo, ocurrido_en: g.creadoEn },
          commandId: g.id,
        })
        if (g.seq !== undefined) await cola.quitar(g.seq)
        sincronizacion.registrar(g)
        enviados++
      } catch (e) {
        if (e instanceof SesionRequerida || e instanceof SinConexion) break
        if (e instanceof ErrorApi && e.esFallaDeServicio) break
        if (e instanceof ErrorApi) {
          await cola.rechazar(g, e.codigo, e.message)
          continue
        }
        throw e
      }
    }
  } finally {
    vaciando = false
  }
  return enviados
}
```

Disparadores de `vaciarCola` (en `LayoutOperacion`, solo si `estacionActiva(local)`): al pasar
`red` a `en_linea`, al recuperar la sesión, cada 30 s si la cola no está vacía y hay conexión, y con el
botón «Enviar ahora». Al terminar con `enviados > 0`: aviso «N comandas enviadas a la nube».

### 5.12 `src/api/rutas.ts`

Un objeto con constructores de rutas y la lista `RUTAS_USADAS` (la lee una prueba de Python que la
compara con `02-api-gateway.md`). Formato exacto de la lista, una cadena por línea:

```ts
export const RUTAS_USADAS = [
  "GET /salud",
  "GET /yo",
  "GET /locales/{local_id}/salon",
  // ... una por cada ruta de la sección 3.3, con el método y la plantilla tal como figuran en 02
] as const
```

Las plantillas de administración son las genéricas de 02 (`GET /locales/{local_id}/admin/{recurso}`,
etc.), no una por recurso.

### 5.13 `public/sw.js`

```js
/* Service worker de la PWA. La compilación reemplaza __VERSION__ (vite.config.ts). */
const VERSION = "__VERSION__"
const CACHE = `pos-${VERSION}`

self.addEventListener("install", (evento) => {
  evento.waitUntil((async () => {
    const respuesta = await fetch("./precache.json", { cache: "no-store" })
    const { archivos } = await respuesta.json()
    const cache = await caches.open(CACHE)
    await cache.addAll(archivos)
  })())
})

self.addEventListener("activate", (evento) => {
  evento.waitUntil((async () => {
    for (const nombre of await caches.keys()) {
      if (nombre.startsWith("pos-") && nombre !== CACHE) await caches.delete(nombre)
    }
    await self.clients.claim()
  })())
})

self.addEventListener("message", (evento) => {
  if (evento.data && evento.data.tipo === "ACTUALIZAR") self.skipWaiting()
})

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request
  const url = new URL(peticion.url)
  if (peticion.method !== "GET" || url.origin !== self.location.origin) return // la API nunca pasa por aquí
  const archivo = url.pathname.split("/").pop() || ""
  if (peticion.mode === "navigate" || archivo === "index.html") {
    evento.respondWith(redPrimero(peticion, "./index.html"))
  } else if (archivo === "config.json") {
    evento.respondWith(redPrimero(peticion, null))
  } else {
    evento.respondWith(cachePrimero(peticion))
  }
})

async function redPrimero(peticion, respaldo) {
  const cache = await caches.open(CACHE)
  try {
    const respuesta = await fetch(peticion, { cache: "no-store" })
    if (respuesta.ok) await cache.put(peticion, respuesta.clone())
    return respuesta
  } catch {
    const guardada = await cache.match(peticion, { ignoreSearch: true })
    if (guardada) return guardada
    if (respaldo) {
      const indice = await cache.match(respaldo)
      if (indice) return indice
    }
    return Response.error()
  }
}

async function cachePrimero(peticion) {
  const guardada = await caches.match(peticion, { ignoreSearch: true })
  if (guardada) return guardada
  const respuesta = await fetch(peticion)
  if (respuesta.ok) {
    const cache = await caches.open(CACHE)
    await cache.put(peticion, respuesta.clone())
  }
  return respuesta
}
```

### 5.14 `vite.config.ts`

```ts
import { createHash } from "node:crypto"
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs"
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

/** Escribe dist/precache.json y pone la versión en dist/sw.js (cambia en cada compilación distinta). */
function precache(): Plugin {
  let salida = "dist"
  return {
    name: "pos-precache",
    apply: "build",
    configResolved(c) {
      salida = path.resolve(c.root, c.build.outDir)
    },
    closeBundle() {
      const excluir = new Set(["sw.js", "precache.json", "config.json"])
      const archivos: string[] = []
      const recorrer = (dir: string) => {
        for (const nombre of readdirSync(dir)) {
          const ruta = path.join(dir, nombre)
          if (statSync(ruta).isDirectory()) recorrer(ruta)
          else {
            const relativa = path.relative(salida, ruta).split(path.sep).join("/")
            if (!excluir.has(relativa)) archivos.push(relativa)
          }
        }
      }
      recorrer(salida)
      archivos.sort()
      const hash = createHash("sha256")
      for (const a of archivos) hash.update(a).update(readFileSync(path.join(salida, a)))
      const version = hash.digest("hex").slice(0, 12)
      writeFileSync(path.join(salida, "precache.json"), JSON.stringify({ version, archivos: archivos.map((a) => `./${a}`) }))
      const sw = path.join(salida, "sw.js")
      writeFileSync(sw, readFileSync(sw, "utf8").replace("__VERSION__", version))
    },
  }
}

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss(), precache()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { port: 8000, strictPort: true },
  preview: { port: 8000, strictPort: true },
})
```

`vitest.config.ts`:

```ts
import { defineConfig, mergeConfig } from "vitest/config"
import vite from "./vite.config"

export default mergeConfig(vite, defineConfig({ test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] } }))
```

`src/test/setup.ts`: `import "fake-indexeddb/auto"`.

### 5.15 `src/pwa/registrarServiceWorker.ts`

```ts
export function registrarServiceWorker(alHaberVersionNueva: (aplicar: () => void) => void): void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return
  const habiaControlador = navigator.serviceWorker.controller !== null
  let recargando = false
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (habiaControlador && !recargando) {
      recargando = true
      window.location.reload()
    }
  })
  void navigator.serviceWorker.register("./sw.js").then((registro) => {
    const avisar = (sw: ServiceWorker) => alHaberVersionNueva(() => sw.postMessage({ tipo: "ACTUALIZAR" }))
    if (registro.waiting && navigator.serviceWorker.controller) avisar(registro.waiting)
    registro.addEventListener("updatefound", () => {
      const nuevo = registro.installing
      nuevo?.addEventListener("statechange", () => {
        if (nuevo.state === "installed" && navigator.serviceWorker.controller) avisar(nuevo)
      })
    })
    window.setInterval(() => void registro.update(), 30 * 60_000)
  })
}
```

`public/manifest.webmanifest`: `{"name": "MISE POS", "short_name": "MISE", "start_url": "./index.html",
"scope": "./", "display": "standalone", "background_color": "#fafafa", "theme_color": "#0a0a0a",
"icons": [{"src": "./favicon.svg", "sizes": "any", "type": "image/svg+xml"}, {"src": "./mise-logo.png",
"sizes": "192x192", "type": "image/png"}]}`. En `index.html`: `<link rel="manifest" href="./manifest.webmanifest">`
y `<meta name="theme-color" content="#0a0a0a">`.

---

## 6. Reciclaje desde `mise-frontend/`

### 6.1 Archivos

Primero copia y luego adapta. «Copiar» significa copiar a la misma ruta bajo `pwa/`.

| Origen (`mise-frontend/`) | Acción |
|---|---|
| `package.json`, `tsconfig*.json`, `eslint.config.js`, `components.json`, `index.html` | Copiar y adaptar (sección 9, fase F0) |
| `Dockerfile`, `nginx.conf`, `README.md`, `.env*`, `dist/`, `node_modules/` | No copiar |
| `public/favicon.svg`, `public/icons.svg` | Copiar |
| `src/assets/branding/*.png` | Copiar; `mise-logo.png` también a `public/` (ícono del manifiesto) |
| `src/assets/images/login/`, `hero.png`, `react.svg`, `vite.svg` | No copiar |
| `src/index.css` | Copiar tal cual |
| `src/lib/utils.ts` | Copiar solo `cn` |
| `src/components/ui/button.tsx`, `dialog.tsx` | Copiar; cambiar `import { cn } from "cn"` por `import { cn } from "@/lib/utils"` |
| `src/components/auth/RequireAuth.tsx` | Reemplazar por `src/sesion/RequiereRol.tsx` (rol del local actual; sin `VITE_BYPASS_AUTH`) |
| `src/components/auth/AutorizacionAdmin.tsx` | Copiar y adaptar: selector de autorizador (`GET L/caja/autorizadores`) + campo de código `type="password"` `inputMode="numeric"` que se vacía después de enviar |
| `src/pages/auth/LoginPage.tsx` | Adaptar: logo, botón de Google (`dibujarBotonGoogle`), y en `modo_dev` botones «Entrar como» mock-dueno, mock-admin, mock-cajero, mock-garzon, mock-garzon2, mock-cocina. Fondo liso, sin la imagen de 2,6 MB |
| `src/pages/auth/AuthCallbackPage.tsx`, `src/pages/menu/MenuPage.tsx` | No copiar |
| `src/pages/pos/TablesPage.tsx`, `components/pos/TableCard.tsx` | Adaptar (sección 7, F4) |
| `src/pages/pos/OrderPage.tsx`, `components/pos/ComandaMesa.tsx`, `CatalogoProductos.tsx`, `ModalProducto.tsx` | Adaptar (F4) |
| `src/pages/caja/PanelCaja.tsx`, `components/caja/*` | Adaptar (F5) |
| `src/layouts/AdminLayout.tsx`, `src/pages/dashboard/*`, `components/dashboard/*` (salvo `ConfiguracionCloud.tsx`) | Adaptar (F6) |
| `components/dashboard/ConfiguracionCloud.tsx` | No copiar |
| `src/services/*` | No copiar: los reemplaza `src/api/*` |

### 6.2 Campos renombrados

| Antes | Ahora |
|---|---|
| `item.producto.nombre`, `item.producto.categoria` | `item.nombre`, `item.categoria` |
| `item.modificador?.nombre` | `item.modificador_nombre` |
| `observacion_libre` | `observacion` |
| `mesa.garzon_asignado_id` | `mesa.garzon_id` |
| `cuarto_cocina_id` | `cuarto_id` |
| `cuarto.impresora: {nombre, direccion, puerto, activa}` | `cuarto.impresora_id` (referencia a una impresora CloudPRNT de `admin/impresoras`) |
| `unidad_medida` | `unidad` |
| `stock_actual`, `stock_minimo` (lectura) | `stock_actual_mil / 1000`, `stock_minimo_mil / 1000` (la escritura sigue siendo `stock_actual`, `stock_minimo`) |
| `receta.ingredientes[].cantidad` (lectura) | `cantidad_mil / 1000` |
| `usuario.usuario_id`, `usuario.activo` | `persona.sub`, `persona.estado === "activo"` |
| `turno.total_debito_pos` (y crédito y notas) | `turno.conciliacion?.total_debito_pos` |
| `producto.imagen_url`, `mesa.reserva_id`, `pedido.estado "anulado"` | No existen: quitar |
| Cantidad pagada por ítem (`calcularCantidadesPagadasPorItem`) | `item.cobrado` |
| Pagos del pedido (`listPagosPorPedido`) | `pedido.pagos` |
| Propina sugerida (`obtenerConfiguracion`) | `LocalDeUsuario.propina_sugerida_pct` de `/yo` (el cajero no puede leer `admin/configuracion`) |

### 6.3 Funciones de servicio antiguas → nuevas

| Antes | Ahora (`src/api/*`) |
|---|---|
| `listMesas`, `getMesa` | `plano(local)` → `GET L/salon` (buscar la mesa por `mesa_id`) |
| `actualizarMesa({estado:"bloqueada"})` | `bloquearMesa(local, mesaId, bloqueada)` |
| `actualizarMesa({garzon_asignado_id})` | `asignarGarzon(local, mesaId, garzonId \| null)` |
| `crearMesa`, `actualizarMesa({numero, capacidad, sector_id})` | `admin.crear(local, "mesas", ...)`, `admin.editar(local, "mesas", id, ...)` |
| `listProductos` | `carta(local, versionGuardada?)` |
| `obtenerOCrearPedido(mesaId)` | comando `pedido.abrir` |
| `obtenerPedido` | `pedido(local, pedidoId)` |
| `agregarItem`, `actualizarItem`, `eliminarItem`, `enviarTanda`, `generarPrecuenta` | comandos `agregar_item`, `modificar_item`, `quitar_item`, `enviar_tanda`, `precuenta` (y `reabrir`, nuevo) |
| `listPedidos({estado:"precuenta"})` | `pendientes(local)` → `GET L/caja/pendientes` |
| `registrarPago` (uno por medio) | **un** comando `registrarPago(local, pedidoId, {medios, tipo_division, items_cobrados?})` con 1 o 2 medios |
| `finalizarCuenta` + tipo de documento en cada pago | comando `finalizar(local, pedidoId, {tipo_documento, receptor?})` |
| `obtenerTurnoActual` (404 → null) | `turnoActual(local)` (404 `TURNO_NO_ABIERTO` → `null`) |
| `abrirTurno`, `registrarConteoEfectivo`, `registrarConciliacionTerminal`, `cerrarTurno` | `abrirTurno`, `conteo`, `conciliacion`, `cerrarTurno` |
| `registrarRetiro({codigo_autorizacion})`, `listRetiros` | `registrarRetiro(local, {monto, motivo, autorizador_id, codigo})`, `retiros(local, turnoId?)` |
| `listSectores`/`crearSector`/`editarSector`, `listCuartos`/..., `listMateriasPrimas`/..., `listRecetas`/`guardarReceta`, `listUsuarios`/`crearUsuario`/... | `admin.listar/crear/editar/eliminar/accion(local, recurso, ...)` |
| `obtenerConfiguracion`/`actualizarConfiguracion` | `admin.listar(local, "configuracion")` / `admin.editar(local, "configuracion", "local", ...)` |
| `setMiPin` | `admin.crear(local, "mi-codigo", {codigo})` |
| `obtenerEstadoCloud`, `enrolarNodo`, `loginWithGoogle`, `exchangeWithNode`, `apiFetch`, `cloudFetch`, `getDeviceId`, `extractErrorMessage` | Eliminar |

Toda escritura de `src/api/*` construye un `Comando` con `crearComando` y lo pasa a `ejecutar`. Las
lecturas usan `leer`.

---

## 7. Pantallas y comportamiento

### 7.1 Arranque, sesión y navegación

- `main.tsx`: `cargarConfig()` y luego render. Si falla, pantalla «No se pudo cargar la configuración
  (config.json)». Después, `registrarServiceWorker` con un aviso fijo «Hay una versión nueva ·
  Actualizar».
- `SesionProvider` (con `useSyncExternalStore` sobre `suscribirSesion`): cuando hay token,
  `GET /yo`; expone `{sesion, yo, local, rol, sinConexionSoloLectura}`. En la estación, después de
  cada `/yo` llama a `guardarSesionDeEstacion`.
- Si no hay token: en `modo_dev`, la pantalla de ingreso con botones; si no, `cargarGoogle(autoSeleccion)`
  con `autoSeleccion = estacionActiva(localGuardado) === null`, luego `intentarIngresoSilencioso()` y
  el botón.
- Si no hay token, no hay red y existe `sesionDeEstacion` vigente para el local guardado: modo sin
  conexión (P17), con aviso fijo «Sin conexión. Ingresa cuando vuelva internet para enviar N comandas».
- Rutas (`createHashRouter`): `/ingresar`, `/locales`, `/sin-acceso`, `/sin-pantalla`,
  `/l/:localId/salon`, `/l/:localId/salon/mesas/:mesaId`, `/l/:localId/caja` (el cobro sigue siendo
  el modal de `PendientesCaja`), `/l/:localId/admin`, `/l/:localId/admin/catalogo`,
  `/l/:localId/admin/salon`, `/l/:localId/admin/cocina`, `/l/:localId/admin/inventario`,
  `/l/:localId/admin/personal`, `/l/:localId/admin/configuracion`, `/l/:localId/admin/reportes`,
  `/l/:localId/admin/reportes/turnos/:turnoId`. `/` lleva al inicio del rol (3.4). Con más de un
  local y ninguno elegido: `/locales`.
- `RequiereRol roles={[...]}` usa el rol del local de la URL; si no corresponde, redirige al inicio
  del rol.
- `LayoutOperacion` (salón y caja): encabezado con local, persona, `BarraConexion` y menú a las
  secciones que permite el rol. `BarraConexion`:
  - sin conexión en un celular: «Sin conexión: usa la caja»;
  - sin conexión en la estación: «Sin conexión: las comandas se guardan en este equipo (N pendientes)»;
  - con mesas sincronizando: «Sincronizando N mesas…»;
  - con sesión vencida y cola pendiente: «Ingresa para enviar N comandas guardadas» con el botón.
- Avisos (toasts) para resultados de comandos:
  - `via: "contingencia"` → «Registrada en contingencia: se aplicará en unos segundos.» y, si fue
    `enviar_tanda`, «No se imprimió: la caja decide si imprimir.»;
  - `via: "cola_local"` → «Guardada en este equipo. Se enviará cuando vuelva internet.»

### 7.2 Salón (`TablesPage`, `TableCard`) — F4

- Datos: `GET L/salon` al entrar; luego `?solo_estado=1` cada 10 s (P18), mezclado por `mesa_id`.
  En la estación, guarda el plano en caché y, sin conexión, lo usa.
- Estado mostrado = `estadoMesa(mesa, [...cola pendiente de esa mesa, ...sincronizacion.comandos])`.
- `TableCard`: número, sector, capacidad, estado (libre, ocupada, precuenta, bloqueada), «Tu mesa» si
  `garzon_id === sub`, y la etiqueta «Sincronizando» o «Guardada en este equipo» cuando corresponde.
- Al tocar una mesa:
  - bloqueada → aviso «La mesa está bloqueada»;
  - en otro caso, ir a `/l/:local/salon/mesas/:mesaId`.
- Dueño, admin y cajero ven en cada tarjeta «Bloquear» o «Desbloquear» (`POST .../bloqueo`).
- Dueño y admin ven «Asignar garzón», con la lista de `GET L/admin/personal` filtrada a
  `estado = activo`, sin invitaciones y con rol dueño, admin, cajero o garzón, más la opción «Sin
  garzón».
- Pestañas de sector, igual que antes.

### 7.3 Comanda (`OrderPage`, `ComandaMesa`, `CatalogoProductos`, `ModalProducto`) — F4

- Carga: la mesa sale del plano. Si la mesa está libre, ejecuta el comando `pedido.abrir` (P19) y usa
  la respuesta: si es 200 con otro `pedido_id`, se queda con ese. Si tiene `pedido_id`, hace
  `GET L/pedidos/{id}` y lo refresca cada 15 s.
- Carta: `GET L/catalogo?version=<la guardada>`. Con `sin_cambios: true` usa la guardada (en memoria
  en celulares; en caché en la estación). Recarga cada 5 min. Solo productos `activo`.
- Vista del pedido = pedido del servidor (o caché) + `aplicar(..., "superponer")` de la cola local y de
  los comandos en sincronización de esa mesa. Las líneas aún no confirmadas llevan la marca
  «pendiente».
- Agregar: `ModalProducto` (modificador opcional, observación). Comando `pedido.agregar_item` con
  `cantidad: 1`, `item_id: ulid()` y `vistaItem` con nombre, categoría, `cuarto_id`,
  `precio_unitario = precio + precio_adicional` y `modificador_nombre`.
- Si la estación va a guardar en la cola local, primero valida con
  `aplicar(vistaActual, c, "validar")` y muestra el error si lo hay.
- Ítems `en_espera`: botones −/+ (`modificar_item` con la cantidad nueva, mínimo 1), editar
  observación y quitar (`quitar_item`). Los ítems `enviado` no se pueden tocar.
- «Enviar a cocina (N)»: `enviar_tanda`. Con la respuesta normal, muestra por cuarto:
  - `encolada` → «Enviada a {cuarto}»;
  - `sin_impresora` → «{cuarto}: sin impresora configurada».
- «Precuenta»: `precuenta`. Si `items_en_espera > 0`, aviso «Hay N ítems que no se enviaron a
  cocina». Luego vuelve al salón.
- Con `PEDIDO_EN_PRECUENTA`, o en una mesa en precuenta: botón «Reabrir mesa» → diálogo «Reabrir la
  mesa deja sin efecto la precuenta. ¿Confirmas?» → `reabrir` con `confirmado: true` (M13).
- Total = `pedido.total` (calculado por el servidor o por `aplicar`).

### 7.4 Caja (`PanelCaja`) — F5

Encabezado: estado del turno (`GET L/caja/turno`; 404 = «Sin turno abierto»). Pestañas:
**Pendientes · Turno · Retiros · Documentos · Conflictos · Impresiones retenidas · Estación**. Si no
hay conexión, todas muestran «Esta sección necesita internet», salvo Estación.

**Pendientes y cobro** (`PendientesCaja`, `FormularioPago`, `DivisionCuenta`, `DivisionPorItems`,
`DivisionPartesIguales`, `MontoLibre`, `DetalleCuenta`, `ResumenPago`, `TarjetaMesaCobro`,
`SeleccionDocumento`, `DatosFactura`, `DocumentoTributario`): conserva el flujo y la interfaz
anteriores con estos cambios:
- Lista: `GET L/caja/pendientes`, unida con el plano para número y sector. Refresca cada 10 s.
  `saldo` y `cobrado` salen del pedido.
- División:
  - `completa` → monto = saldo;
  - `items` → máximo `cantidad - cobrado` por ítem; monto = `montoPorItems`;
  - `partes_iguales` → `dividirPartesIguales(saldo, personas)` con 2 a 20 personas; qué parte se pagó
    vive solo en memoria, como antes;
  - `monto_libre` → de 1 a saldo.
- Propina sugerida = `propinaSugerida(monto, propina_sugerida_pct)`, editable.
- `FormularioPago`: 1 o 2 medios (no más).
  - Débito o crédito exigen código del terminal.
  - Efectivo exige efectivo recibido ≥ monto + propina; el vuelto se muestra antes como vista previa.
  - Si hay 2 medios, el segundo cubre lo que falta.
  - Confirmar = **un** comando `POST .../pagos` con `medios`, `tipo_division` e `items_cobrados`
    (solo con `items`).
  - Con la respuesta, actualiza `pagado` y `saldo`.
- Con saldo 0: elegir boleta o factura (factura con `rutValido` y razón social) → `POST .../finalizar`.
  Si `pedido.total === 0`: botón «Liberar mesa sin consumo» → `finalizar` con solo `{pedido_id}`.
- Documento: después de finalizar, `GET L/caja/documentos/{venta_id}` cada 3 s hasta 60 s.
  - `pendiente`/`enviando` → «Emitiendo…»;
  - `emitido` → «Folio N» y botón «Reimprimir»;
  - `rechazado` → «Rechazado: {motivo_rechazo}»;
  - `fallido` → «No se pudo emitir; se reintenta automáticamente».
- Quitar el `console.log` de «Imprimir precuenta» y ese botón (P21).

**Turno** (`CierreCaja`):
- Sin turno: monto de apertura → `POST L/caja/turnos`.
- Abierto: primer conteo → `POST .../conteo`. Si `requiere_segundo_conteo`, aviso «La diferencia
  supera lo tolerado: cuenta de nuevo el efectivo» (sin mostrar cifras) y segundo conteo.
- Conciliación de terminal (débito, crédito, notas de crédito), corregible mientras el turno esté
  abierto.
- «Cerrar turno», habilitado cuando hay conteo (y segundo si se pidió) y conciliación. Muestra el
  `ResultadoCierre` y marca «fuera de umbral» si corresponde.
- **Nunca** muestra totales esperados con el turno abierto: la API no los entrega.

**Retiros** (`RetirosCaja`, `AutorizacionAdmin`):
- Lista: `GET L/caja/retiros`.
- Nuevo: monto, motivo, autorizador (`GET L/caja/autorizadores`; si está vacío, «Ningún dueño o admin
  tiene código de autorización definido») y código.
- Errores:
  - `CODIGO_AUTORIZACION_INVALIDO` → «Código incorrecto. Te quedan N intentos»;
  - `AUTORIZACION_BLOQUEADA` → mensaje del servidor.

**Documentos**: `GET L/caja/documentos` del turno abierto, con tabla de estado, folio y total, y
«Reimprimir» si está emitido. En Documentos y Retiros, `404 TURNO_NO_ABIERTO` se muestra como «Sin
turno abierto», no como error.

**Conflictos**:
- Lista: `GET L/caja/conflictos`, con un selector «Ver resueltos» (`?todos=1`).
- Muestra la operación en palabras («Agregar ítem», «Abrir mesa»…), la mesa (de `comando.cuerpo.mesa_id`),
  el motivo, quién y cuándo (`comando.nombre`, `comando.ocurrido_en`).
- Acciones «Marcar resuelto» y «Descartar», con nota opcional.

**Impresiones retenidas**: tarjetas con mesa, cuarto, garzón, hora y líneas, y botones «Imprimir
ahora» (liberar) y «Descartar».

**Estación** (dueño, admin, cajero):
- Si el equipo no es estación: lista `estaciones_caja` del local (de `/yo`; con dueño o admin,
  nombres desde `GET L/admin/estaciones`) y botón «Usar este equipo como {estación}»
  (`activarEstacion`).
- Si lo es: nombre, comandas guardadas (operación, mesa, hora, registrado por), botón «Enviar ahora»,
  lista de rechazados al enviar (mensaje y «Descartar») y «Dejar de usar este equipo como estación»
  (solo con la cola vacía).

### 7.5 Administración (`AdminLayout`, `pages/dashboard/*`) — F6

Menú: Inicio · Catálogo · Salón y cocina · Inventario · Personal · Configuración · Reportes, más
enlaces a Salón y Caja.

| Página | Contenido |
|---|---|
| Inicio (`DashboardPage`) | Turno actual (`GET L/caja/turno`) y resumen de hoy (`GET L/reportes/dias/{hoySantiago()}`) con accesos a cada sección |
| Catálogo (`CatalogoPage` y sus componentes) | Lista con filtros por categoría y estado; crear y editar producto: nombre, categoría (4 fijas), precio entero, cuarto (de `admin/cuartos`), activo, descripción, modificadores (los existentes conservan `modificador_id`). Sin borrar: «Desactivar» |
| Salón y cocina (`OperacionPage`, `SectoresMesas`, `CuartosImpresoras`, formularios) | Sectores (nombre, activo); mesas (sector, número, capacidad, activa); cuartos (nombre, descripción, activo, impresora); **impresoras** (nuevo): nombre, modelo, activa. Al crear o rotar clave: diálogo «Copia estos datos ahora; la clave no se volverá a mostrar» con usuario (`usuario_cloudprnt`), clave y la URL CloudPRNT `{api_url}/impresion/{tenant_id}/{local_id}/{impresora_id}` |
| Inventario (`InventarioPage` y componentes) | Materias primas (nombre, unidad, stock actual y mínimo con hasta 3 decimales, activo; aviso si stock < mínimo) y recetas por producto (ingredientes y cantidad). Quita lo que no esté en el contrato (movimientos, ajustes) |
| Personal (`UsuariosPage`, `ListaUsuarios`, `FormularioUsuario`) | Lista de personas e invitaciones. Invitar (email, nombre, rol; el admin no ve la opción dueño). Editar nombre, rol y estado (activo o archivado); sin controles de rol y estado para uno mismo. Cancelar invitación |
| Configuración (`ConfiguracionPage`, `ConfiguracionLocal`, `ConfiguracionCaja`) | Datos del local: nombre, marca, propina sugerida %, umbral % (hasta 2 decimales), umbral mínimo, impresora de caja. Estaciones de caja (crear y eliminar). «Mi código de autorización» (4 a 8 dígitos, `type="password"`) |
| Reportes (nueva, puede reutilizar `OperacionResumen`) | Turnos con filtro desde y hasta; detalle del turno (caja, resumen, por garzón, retiros, documentos por estado); resumen de un día |

---

## 8. Pruebas

### 8.1 Unitarias de la PWA (`pwa/src/**/*.test.ts`, `npm run test`)

| Archivo | Casos |
|---|---|
| `lib/ulid.test.ts` | 26 caracteres; cumple `esUlid`; el prefijo de tiempo crece con la hora |
| `lib/dinero.test.ts` | `propinaSugerida(16500, 10) = 1650`; `propinaSugerida(1005, 10) = 101`; `dividirPartesIguales(100, 3) = [34, 33, 33]`; errores con 1 y 21 personas y con total < personas; `montoPorItems` con `cobrado`, tope por saldo y líneas repetidas sumadas; error al exceder lo disponible |
| `api/cliente.test.ts` (simula `fetch`) | Envía `Authorization`, `X-Command-Id` y `Content-Type` solo cuando corresponde; 401 → `SesionRequerida`; error de la Lambda → `ErrorApi` con `codigo`, `mensaje` y `detalle`; error de `fetch` → `SinConexion`; `x-comando-repetido` → `repetido: true` |
| `api/comandos.test.ts` | 409 de negocio: lanza sin reintentar; `CONFLICTO_CONCURRENCIA`: reintenta una vez con el mismo ID; 503 dos veces en una comanda → `POST /contingencia/comandas` con `{operacion, local_id, cuerpo, ocurrido_en}` y el mismo `X-Command-Id`; 503 dos veces en una escritura que no es comanda → lanza; contingencia caída en la estación → `cola_local`; contingencia caída sin estación → `SinConexion("Sin conexión: usa la caja")`; estación sin conexión → `cola_local` sin llamar a `fetch`; 202 → `via: "contingencia"` y mesa sincronizando |
| `offline/cola.test.ts` | Orden por `seq`; mismo ID dos veces = una entrada; `contar` por local; `rechazar` mueve a rechazados |
| `offline/sincronizar.test.ts` | `vaciarCola` envía en orden; se detiene en 503 y en `SesionRequerida`; un 4xx va a rechazados y sigue; `verificar` termina cuando el pedido refleja los comandos, quita los que tienen conflicto y avisa a los 120 s |
| `offline/pedidoLocal.test.ts` | Cada regla de la tabla 5.10 con su código; en `superponer`, aplicar dos veces el mismo comando = una vez; `huella` estable ante el orden de los ítems |

### 8.2 Python (`.venv\Scripts\python -m pytest -q`)

- `tests/dominio/test_pwa_contrato.py`:
  1. Cada cadena de `RUTAS_USADAS` (leída de `pwa/src/api/rutas.ts` con la expresión
     `"(GET|POST|PATCH|DELETE) (/[^"]*)"`) existe en `rutas_api.rutas()`.
  2. Ninguna empieza con `/impresion/`, `/publico/` ni `/webhooks/`, salvo `GET /salud`.
  3. Las cadenas de `OPERACIONES_COMANDA` (leídas de `pwa/src/api/comandos.ts`) son exactamente las
     claves de `pos_dominio.operaciones.pedidos.CONTINGENCIA`.
- `tests/dominio/test_servidor_local.py` (servidor de la sección 9, F3, en un hilo y puerto libre):
  1. `/salud` responde 200.
  2. `OPTIONS` devuelve los encabezados CORS.
  3. `/yo` sin token responde 401; con `dev:mock-cajero` responde 200 con `local_01`.
  4. Abrir `m03` con `X-Command-Id` responde 201.
  5. Con `rutas_normales` caídas, una comanda responde 503 y por `/contingencia/comandas` responde
     202; al levantar la falla, `GET` del pedido muestra el ítem.

### 8.3 Comandos por fase

```
cd pwa
npm run lint
npm run test
npm run build
cd ..
.venv\Scripts\python -m pytest -q tests/dominio/test_pwa_contrato.py tests/dominio/test_servidor_local.py tests/dominio/test_scripts_cloudshell.py
```

Antes del commit final de F7 y de F8, la suite completa en segundo plano:
`.venv\Scripts\python -m pytest -q`.

---

## 9. Fases

| Fase | Trabajo | Listo cuando | Commit |
|---|---|---|---|
| **F0** Esqueleto | Ver detalle abajo | `npm run build` y `npm run lint` pasan con una pantalla «MISE» | `feat(pwa): esqueleto de la PWA v2` |
| **F1** Núcleo sin pantallas | Todo el código de la sección 5 salvo 5.13 a 5.15: `config`, `lib/*`, `gis.d.ts`, `sesion/google.ts`, `offline/*` (incluido `pedidoLocal.ts` según la tabla 5.10), `api/cliente.ts`, `api/comandos.ts`, `api/rutas.ts`, `api/tipos.ts` (3.2) y `api/salon.ts`, `pedidos.ts`, `caja.ts`, `admin.ts`, `reportes.ts` (una función por ruta de 3.3; escrituras con `crearComando` + `ejecutar`). Todas las pruebas de 8.1 y `test_pwa_contrato.py` | Pruebas en verde y `npm run build` | `feat(pwa): cliente de la API, contingencia y cola local` |
| **F2** Sesión y armazón | `SesionProvider`, `useSesion`, `RequiereRol`, enrutador (7.1), `LoginPage`, `SinAcceso`, `SinPantalla`, `SelectorLocalPage`, `LayoutOperacion`, `BarraConexion`, `Notificaciones`, `useSondeo`, `useEnLinea`, y los disparadores de `vaciarCola` y `sincronizacion.verificar` (5.11) | `npm run build` y `npm run lint`; la pantalla de ingreso se ve en `npm run dev` | `feat(pwa): sesión, navegación y estado de conexión` |
| **F3** Servidor local | `scripts/servidor_local.py` (detalle abajo) y su prueba | Prueba en verde; la PWA (`npm run dev`) ingresa como mock-garzon | `feat(herramientas): servidor local que emula el API Gateway` |
| **F4** Salón y comanda | 7.2 y 7.3 | Lista 10.1 pasos 1 a 3 | `feat(pwa): salón y comanda` |
| **F5** Caja | 7.4 | Lista 10.1 pasos 4 a 9 | `feat(pwa): caja` |
| **F6** Administración | 7.5 | Lista 10.1 pasos 10 a 13 | `feat(pwa): administración y reportes` |
| **F7** PWA y publicación | 5.13 a 5.15, manifiesto y cambios en los scripts (detalle abajo) | `npm run build` genera `precache.json`; `npm run preview` funciona sin conexión tras la primera carga; pruebas de scripts en verde | `feat(despliegue): publicar la PWA en S3` |
| **F8** Documentos | Detalle abajo | Suite completa en verde | `docs(migracion): PWA v2 y corte de red por contingencia` |

**F0 en detalle:**
1. Crear `pwa/` con los archivos de 6.1 marcados «Copiar».
2. `package.json`:
   - `name: "mise-pwa"`;
   - scripts `dev: "vite"`, `build: "tsc -b && vite build"`, `preview: "vite preview"`,
     `test: "vitest run"`, `lint: "eslint ."`;
   - quitar la dependencia `cn`.
3. `npm install`, luego `npm i idb` y `npm i -D vitest jsdom fake-indexeddb`. Si npm informa un
   conflicto de dependencias con `vite`, repetir con `--legacy-peer-deps` y anotarlo en el commit.
4. `tsconfig.app.json`: agregar `"strict": true`. `tsconfig.node.json`: incluir `vite.config.ts` y
   `vitest.config.ts`.
5. `vite.config.ts` y `vitest.config.ts` de 5.14 (el plugin ya puede estar; `public/sw.js` vacío con
   la línea `const VERSION = "__VERSION__"`).
6. `pwa/config.example.json` = `{"api_url": "http://localhost:8001", "google_client_id": "", "modo_dev": true}`.
7. Agregar a `.gitignore` de la raíz: `pwa/public/config.json` y `google-client-id.txt`.
8. `pwa/README.md` con «Desarrollo»:
   - `copy config.example.json public\config.json`;
   - `python ..\scripts\servidor_local.py` en otra terminal;
   - `npm run dev`;
   - abrir `http://localhost:8000`.

**F3 en detalle — `scripts/servidor_local.py`:**
- Uso: `python scripts/servidor_local.py [--puerto 8001] [--origen http://localhost:8000]`.
- Reutiliza `TransporteSimulado` de `scripts/validar_despliegue.py` (moto, tablas, colas, semilla
  mock y las funciones cargadas): usa su lista `rutas`, su `esperar()` y sus clientes. Agrega el
  bombeo de `contingencia-comandas.fifo` → `drenador-contingencia` (mismo patrón que el de
  `dte-emision`: recibir hasta 10, invocar, borrar los que no fallaron). Lo llama después de
  `esperar()` en cada petición.
- `http.server.HTTPServer` de **un solo hilo** (moto no es seguro entre hilos). Expone
  `crear_servidor(puerto: int, origen: str) -> HTTPServer` para que la prueba lo levante en un hilo y
  lo detenga con `shutdown()`; `main()` solo lee los argumentos y llama a `serve_forever()`.
- Cada petición:
  1. `OPTIONS` → 204 con `Access-Control-Allow-Origin: <origen>`,
     `Access-Control-Allow-Headers: authorization,content-type,x-command-id`,
     `Access-Control-Allow-Methods: GET,POST,PATCH,DELETE`,
     `Access-Control-Max-Age: 600`.
  2. Busca la ruta. Sin coincidencia → 404 `{"message":"Not Found"}`.
  3. Si la ruta es privada (columna JWT de `rutas_api.rutas()`), exige
     `Authorization: Bearer dev:<sub>`; si no está → 401 `{"message":"Unauthorized"}`. Con él arma
     `claims = {sub, email: "<sub>@demo.invalid", email_verified: "true", name: <sub>}`.
  4. Arma el evento 2.0 (`routeKey`, `headers` en minúsculas, `pathParameters`,
     `queryStringParameters`, `body` como texto, `requestContext.authorizer.jwt.claims`), invoca la
     función y devuelve su `statusCode`, `headers` y `body`.
  5. Agrega a toda respuesta `Access-Control-Allow-Origin` y
     `Access-Control-Expose-Headers: x-comando-repetido`.
- Fallas para probar contingencia:
  - `POST /__dev/fallas` con `{"rutas_normales": bool, "dynamodb": bool}` (y `GET` devuelve el
    estado).
  - `rutas_normales: true`: toda ruta privada salvo `GET /yo` y `POST /contingencia/comandas`
    responde 503 `{"message":"Service Unavailable"}`.
  - `dynamodb: true`: pone `SIMULAR_FALLA_DYNAMODB=true` en el proceso, así `pedidos` responde 202 y
    el drenador reintenta hasta que se quite.
- Al iniciar imprime: URL, origen permitido, personas mock (mock-dueno con código 1234, mock-admin
  con 4321, mock-cajero, mock-garzon, mock-garzon2, mock-cocina) y la línea para el simulador de
  impresora:
  `POS_CLAVE_IMPRESORA=mock-clave-cocina python scripts/simulador_impresora.py --api http://localhost:8001 --impresora imp_cocina`.

**F7 en detalle:**
1. `infra/cloudshell/publicar_pwa.sh` (nuevo, idempotente):
   - lee `valores-despliegue.env`;
   - exige `pwa/dist/index.html`;
   - toma `GOOGLE_CLIENT_ID` del entorno o de `google-client-id.txt`;
   - escribe un `config.json` **en un directorio temporal** (`mktemp -d`; nunca dentro de `pwa/dist`) =
     `{"api_url": URL_API, "google_client_id": ..., "modo_dev": false}` (con `python3 -c` y `json.dumps`);
   - sube, **en este orden**:
     1. `assets/` con `--cache-control "public,max-age=31536000,immutable"`;
     2. los demás archivos estáticos con `max-age=86400`, excluyendo `config.json`, `index.html`,
        `sw.js`, `precache.json` y `manifest.webmanifest`;
     3. `manifest.webmanifest` (`application/manifest+json`), `sw.js` (`text/javascript`),
        `precache.json` (`application/json`) y el `config.json` temporal (`application/json`), todos
        con `no-cache`;
     4. al final `index.html` (`text/html; charset=utf-8`, `no-cache`);
   - sin `--delete`;
   - imprime `PWA: $URL_SITIO/index.html`.
2. `desplegar.sh`:
   - después de `: > "$VALORES"`, si `GOOGLE_CLIENT_ID` está vacío y existe `google-client-id.txt`,
     leerlo (sin espacios);
   - `guardar GOOGLE_CLIENT_ID "${GOOGLE_CLIENT_ID:-}"`;
   - el autorizador usa ese valor como hoy;
   - antes de «==> Listo»: si existe `pwa/dist/index.html`, `paso "15. PWA"` y
     `bash infra/cloudshell/publicar_pwa.sh`;
   - en el resumen, línea `PWA:`.
3. `configurar_google.sh`:
   - guarda el ID en `"$RAIZ/google-client-id.txt"` (con `RAIZ` = raíz del paquete);
   - si existe `pwa/dist/index.html`, ejecuta `GOOGLE_CLIENT_ID=<id> bash infra/cloudshell/publicar_pwa.sh`.
4. `scripts/paquete_cloudshell.py`:
   - agregar `"pwa/dist"` a `INCLUIR`;
   - no convertir finales de línea dentro de `pwa/dist/`;
   - partes con dos dígitos (`pos-parte-01.txt`) y máximo 99.

   Ajustar su prueba (`2 <= len(partes) <= 99`).
5. `tests/dominio/test_scripts_cloudshell.py`: `bash -n` también para `publicar_pwa.sh`.
   `test_desplegar_simulado.py` debe pasar con y sin `pwa/dist` (con `pwa/dist`, la AWS CLI falsa
   acepta las subidas).

**F8 en detalle:**
1. `05-validacion.md`, fila S9:
   - con la PWA: DevTools → Network → **Offline** en la estación de caja → registrar comandas →
     recargar (sigue funcionando) → **No throttling** → ingresar;
   - resultado esperado: la cola se envía **por `POST /contingencia/comandas`**, en orden; sin
     duplicados (`X-Command-Id`); las comandas enviadas a cocina aparecen en **Impresiones
     retenidas**; los rechazos, en la bandeja de conflictos con correo al dueño; un celular sin
     conexión muestra «Sin conexión: usa la caja»;
   - quitar «pendiente de la PWA» en las filas S9 y del criterio de término.
2. `arquitectura.html`: en el diagrama de contingencia (carril C), cambiar «reenvía por la ruta normal»
   por «reenvía por la ruta de contingencia», en el texto y en el `aria-label`.
3. `06-despliegue-cloudshell.md`:
   - nueva sección «Publicar la PWA»: en tu PC `cd pwa && npm ci && npm run build`, luego
     `python scripts/paquete_cloudshell.py`; en CloudShell, `desplegar.sh` la publica sola (o
     `bash infra/cloudshell/publicar_pwa.sh`);
   - abrir `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/index.html`;
   - partes `pos-parte-01.txt`…
4. `README.md` de migración: enlazar este documento; quitar «PWA» de pendientes; dejar el ID de
   cliente de Google.
5. `02-api-gateway.md` no cambia.

---

## 10. Validación de aceptación

### 10.1 Con el servidor local (sin AWS ni Google)

Terminal 1: `python scripts/servidor_local.py`. Terminal 2: `cd pwa && npm run dev`. Navegador:
`http://localhost:8000`.

1. Como **mock-garzon**:
   - salón → mesa 3 → se abre;
   - agregar pizza con modificador y 2 bebidas;
   - enviar → «Enviada a Cocina» y «Enviada a Barra»;
   - en una terminal 3, el simulador de impresora de cocina imprime la comanda.
2. Precuenta → la mesa queda en precuenta → agregar → «Reabrir mesa» con confirmación funciona.
3. En la ventana de DevTools: **Offline** en el celular simulado (sin estación) → agregar → «Sin
   conexión: usa la caja» y no queda nada guardado.
4. Como **mock-cajero**:
   - Caja → Turno → abrir con $50.000;
   - Pendientes muestra la mesa 3;
   - cobrar mixto (efectivo + débito) con propina;
   - boleta → «Folio 1» → Reimprimir.
5. Cobro por ítems y en partes iguales en otra mesa: el saldo baja correctamente; un monto que no
   corresponde muestra el mensaje del servidor.
6. Retiros:
   - autorizador mock-dueno con código 1234 → retiro registrado;
   - código incorrecto → «Te quedan N intentos»;
   - 5 veces → bloqueo.
7. Turno: conteo, conciliación y cierre, con el resultado visible solo al cerrar.
8. Contingencia:
   - `curl -X POST http://localhost:8001/__dev/fallas -d "{\"rutas_normales\": true}"`;
   - el garzón agrega un ítem → «Registrada en contingencia» y la mesa «Sincronizando»;
   - quitar la falla → el ítem aparece y la mesa deja de sincronizar;
   - si se envió a cocina, la caja ve el trabajo en **Impresiones retenidas** → «Imprimir ahora».
9. Estación:
   - el cajero activa «Caja principal»;
   - DevTools **Offline** → abrir mesa 5, agregar ítems y enviar → «Guardada en este equipo (N)»;
   - recargar sin conexión → sigue en modo sin conexión;
   - **No throttling** → ingresar → «N comandas enviadas» → la mesa 5 aparece con sus ítems y sus
     impresiones retenidas.
10. Como **mock-admin**: crear producto con modificador; editar precio → el salón recarga la carta
    (versión nueva).
11. Personal:
    - invitar un email y luego cancelar la invitación;
    - cambiar el rol de mock-garzon2;
    - no hay controles de rol para uno mismo;
    - el admin no ve la opción «dueño».
12. Impresoras: crear una → la clave aparece una vez; rotar clave → clave nueva. Cuarto con
    impresora asignada.
13. Reportes: el turno cerrado del paso 7 con totales y ventas por garzón; resumen del día.
14. `npm run build && npm run preview`: carga, DevTools **Offline**, recarga → la PWA abre desde el
    service worker.

### 10.2 En la nube (cuando exista el ID de cliente de Google)

1. En tu PC: `cd pwa && npm ci && npm run build`, y luego `python scripts/paquete_cloudshell.py`.
2. En CloudShell:
   - subir y descomprimir el paquete;
   - `bash infra/cloudshell/configurar_google.sh <ID>` (publica la PWA con el ID);
   - o `GOOGLE_CLIENT_ID=<ID> bash infra/cloudshell/desplegar.sh`.
3. Abrir `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/index.html`, ingresar con el email de
   `EMAIL_DUENO_REAL` y repetir 10.1 pasos 1, 4, 8 y 9. Para el paso 8, usar el simulacro S2 de 05
   (concurrencia reservada 0 en `pedidos`) en lugar de `__dev/fallas`.
