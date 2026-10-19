# 00 — Inventario del POS local

Fase 0 de la migración a AWS Lambda. Este documento describe el sistema **tal como está hoy**, sin
proponer todavía el modelo de datos. Sirve de base para el punto de control 1.

**Qué se leyó**

| Componente | Ubicación | Versión leída |
|---|---|---|
| Backend `pos-api` (FastAPI) | `mise-backend/app/` | commit `bb22c60` **más 24 archivos modificados y 16 rutas nuevas sin commitear** |
| Base de datos (PostgreSQL 16) | `mise-basededatos/init/01_schema.sql`, `02_seed.sql` | ídem |
| Frontend (submódulo, React 19 + Vite 8) | `mise-frontend/src/` | commit `e084510` **más 64 rutas con cambios sin commitear** |
| Orquestación local | `docker-compose.yml`, `mise-nginx/` | ídem |
| Nube v1 previa (fleet híbrido) | `aws-upload/` y `../../aws/ESTADO.md` | sin versionar |
| Requisitos | `../../requisitos_MISE_v1.docx.txt` | 2026-09-29 |

> El comportamiento "local actual" que fijarán las pruebas de caracterización es el del **árbol de
> trabajo**, no el del último commit. Ver la pregunta P2.

---

## 0. Resumen: lo que bloquea o condiciona la migración

1. **CloudFront está denegado en el Learner Lab** (`aws/ESTADO.md` §6.1, verificado por el equipo en
   septiembre). La decisión cerrada lo usa para el sitio. Sin HTTPS no funcionan el service worker ni
   el inicio de sesión con Google Identity Services. → **C1 / P1**.
2. **El código local es la arquitectura híbrida anterior** (nodo en el restaurante con Postgres,
   outbox y sincronización cada 30 s). Toda esa parte se elimina, no se migra. → **C2–C4**.
3. **Varias reglas que el prompt pide caracterizar no existen en el código local**: anulación con
   código, descuentos (y por lo tanto "propina antes de descuentos"), reservas, impresión, documentos
   tributarios, pedidos externos y reportes. → **§9 / P3**.
4. **Gran parte de la lógica de caja vive en el frontend** (división de cuenta, pago mixto,
   propina sugerida). Hay que moverla al dominio y caracterizarla desde el TypeScript. → **§3.2**.
5. **El backend nunca recibe el tipo de documento ni los datos de facturación**: el frontend los pide
   *después* del pago y no los envía. Sin eso, `emision-dte` no tiene qué emitir. → **D8 / P9**.

### Decisiones del punto de control 1 (2026-10-13)

| Pregunta | Decisión del equipo | Cómo queda aplicada |
|---|---|---|
| P1 Sitio | CloudFront no se podrá usar nunca en este entorno (confirmado por el equipo el 2026-10-15). S3, salvo que servirlo por API Gateway sea mucho más barato | No lo es (ver abajo). El sitio se sirve desde **S3 por su endpoint REST con HTTPS** (`https://<bucket>.s3.us-east-1.amazonaws.com/index.html`). CloudFront queda fuera del proyecto, no como pendiente |
| P2 Línea base | No se commitea el trabajo anterior. La rama `feature/migracion-lambdas` es la v2 oficial; lo anterior queda **deprecado** | La rama sale de `main` (`bb22c60`). Solo se commitea código nuevo; los cambios sin commitear de la versión anterior no se tocan ni se incluyen. El frontend v2 se copia dentro de este repositorio, sin depender del submódulo |
| P3 Alcance | Primero, solo las funciones que ya existen en el POS local. El código no se copia: se diseña para Lambda y corrige los errores de lógica actuales | Quedan **fuera** en esta etapa: anulación con código, descuentos, reabrir mesa, traslado de ítems, reservas, pedidos externos, cierre observado o autorizado, propinas por garzón. Los mecanismos de plataforma que exige la migración (idempotencia, eventos, impresión, documento tributario simulado, contingencia, reportes del turno) sí entran. **D1–D21 se corrigen**, cada uno con su prueba |
| P4 Defectos | Corregir (de la respuesta a P3) | Ver §10 |
| P6/P7 Personal y catálogo | El dueño puede tener varios locales. Admin y funcionarios son por local; si un admin trabaja en dos locales, tiene una asignación en cada uno. **El catálogo es por local** | Modelo de membresías por persona y local en `01-modelo-dynamodb.md` |
| P9 Documento | Se pidió explicación | La propuesta queda en `01`, para revisar en el punto de control 2 |

**Costo del sitio: S3 frente a API Gateway.** Supuesto: 3 locales × 10 equipos × 5 cargas al día ×
30 días = 4.500 cargas al mes, con unos 8 archivos por carga = 36.000 peticiones.

| | Peticiones | Cómputo | Total al mes |
|---|---|---|---|
| S3 (GET, USD 0,0004 por 1.000) | USD 0,014 | — | **≈ USD 0,014** |
| API Gateway HTTP (USD 1 por millón) + Lambda arm64 | USD 0,036 | ≈ USD 0,010 | **≈ USD 0,046** |

La transferencia de datos cuesta lo mismo en los dos casos. API Gateway sale unas **3 veces más
caro**, además de obligar a pasar binarios por Lambda en base64. Se usa S3.

---

## 1. Arquitectura actual

```
navegador ──► mise-nginx (:80) ──► mise-frontend (nginx estático, SPA)
                   │
                   └── /api/* ──► mise-backend (uvicorn + FastAPI, :4000) ──► PostgreSQL 16
                                        │
                                        └── tarea de fondo cada 30 s ──► API Gateway "mise-pos-api" (nube v1)
```

El backend sigue una arquitectura hexagonal razonablemente limpia:

| Capa | Ubicación | Dependencias |
|---|---|---|
| Entidades | `app/domain/entities.py` (dataclasses) | ninguna |
| Errores de dominio | `app/domain/exceptions.py` | ninguna |
| Puertos | `app/application/ports.py` (ABC) | entidades |
| Casos de uso | `app/application/use_cases/*.py` | puertos, entidades |
| Adaptadores HTTP | `app/infrastructure/api/routers/*.py`, `schemas.py`, `deps.py` | FastAPI, Pydantic |
| Adaptadores de datos | `app/infrastructure/repositories/*.py`, `db.py` | psycopg2 |
| Seguridad | `app/infrastructure/security.py` | PyJWT, hashlib |
| Sincronización con la nube | `app/infrastructure/cloud/node_sync.py` | PyJWT, cryptography, asyncio |

Esto facilita la Fase 2: los casos de uso ya dependen de puertos, no de Postgres. Pero **varias reglas
de negocio están escritas en SQL dentro de los repositorios** (§3.1), y esas hay que subirlas al
dominio.

---

## 2. Endpoints

Convenciones de la tabla:

- **Roles**: `todos` = cualquier usuario con sesión válida, sin importar el rol. `D/A` = dueño y
  admin. `D/A/C` = dueño, admin y cajero.
- **Errores locales**: `ValidationError` → 400, `NotFoundError` → 404, `ForbiddenError` → 403,
  `UnauthorizedError` → 401, siempre como `{"error": "..."}`. Los errores de Pydantic salen como 422
  con `{"detail": [...]}` y los de `HTTPException` como `{"detail": "..."}`. El frontend
  (`services/apiError.ts`) solo entiende `{"error"}`.
- **Destino**: la función Lambda a la que se propone mover la ruta. Es tentativo hasta la Fase 1.

### 2.1 Autenticación

| Método y ruta | Roles | Entrada | Salida | Reglas | Tablas | Destino |
|---|---|---|---|---|---|---|
| `POST /api/auth/login` | sin auth | `{email, nombre?, proveedor?}` | `{usuario, token}` | **Legado**: confía en el email que manda el cliente y **crea la cuenta como garzón si no existe**. Rechaza inactivos (403). | usuarios | **Se elimina** |
| `POST /api/v1/auth/login-google` | sin auth | `{google_jwt, device_id?}` | `{usuario, device_token}` | Verifica firma contra el JWKS de Google, `aud` = `GOOGLE_CLIENT_ID`, `iss` ∈ {`https://accounts.google.com`, `accounts.google.com`}, `email_verified`. Busca por email (minúsculas): 401 si no existe (no hay autorregistro), 403 si inactivo. Emite un `device_token` HS256 propio de 12 h. `device_id` se acepta y se ignora. | usuarios | Reemplazado por el autorizador JWT + una ruta `GET /yo` |
| `GET /api/health` | sin auth | — | `{"status":"ok"}` | No verifica la base de datos. | — | `GET /salud` (sí verificará DynamoDB) |

### 2.2 Usuarios

| Método y ruta | Roles | Entrada | Salida | Reglas | Tablas | Destino |
|---|---|---|---|---|---|---|
| `GET /api/usuarios` | todos | — | `[Usuario]` por nombre | Cualquier rol, incluido cocina, lista a todo el personal con email. | usuarios | administracion |
| `POST /api/usuarios` | D/A | `{nombre, email, rol, proveedor_auth?}` | 201 `Usuario` | Nombre y email no vacíos; email en minúsculas y único; rol ∈ {dueno, admin, cajero, garzon, cocina}. **Un admin puede crear un dueño** (D16). | usuarios | administracion |
| `GET /api/usuarios/me` | todos | — | `Usuario` | Perfil propio desde el token. | usuarios | `GET /yo` |
| `GET /api/usuarios/{id}` | todos | — | `Usuario` | 404 si no existe. | usuarios | administracion |
| `PATCH /api/usuarios/{id}` | D/A | `{nombre?, rol?, activo?}` | `Usuario` | Nombre no vacío; rol válido. **Un admin puede cambiar su propio rol a dueño** (D16). | usuarios | administracion |
| `DELETE /api/usuarios/{id}` | D/A | — | `{usuario, eliminado}` | Si tiene historial (pedidos como garzón, mesa asignada, turnos abiertos o cerrados, retiros hechos o autorizados) lo **desactiva**; si no, lo borra. No revisa pagos. | usuarios + 4 tablas con `EXISTS` | administracion |
| `POST /api/usuarios/me/pin` | D/A | `{pin}` | 204 | 4 a 8 dígitos. PBKDF2-HMAC-SHA256, 200 000 iteraciones, sal aleatoria de 16 bytes, guardado como `sal_hex$hash_hex`. | usuarios | administracion |

### 2.3 Sectores y mesas

| Método y ruta | Roles | Entrada | Salida | Reglas | Tablas | Destino |
|---|---|---|---|---|---|---|
| `GET /api/sectores` | todos | — | `[Sector]` por nombre | — | sectores | salon |
| `POST /api/sectores` | D/A | `{nombre, activo=true}` | 201 `Sector` | Nombre no vacío. Nombre único en BD: un duplicado da **500** (D15). | sectores | administracion |
| `PATCH /api/sectores/{id}` | D/A | `{nombre?, activo?}` | `Sector` | Nombre no vacío. | sectores | administracion |
| `GET /api/mesas` | todos | — | `[Mesa]` con `sector_nombre` | JOIN con sectores; orden sector, número. | mesas, sectores | salon |
| `POST /api/mesas` | D/A | `{sector_id, numero, capacidad=4}` | 201 `Mesa` | número > 0, capacidad > 0, sector existe. `(sector, número)` único en BD: duplicado da **500** (D15). | mesas | administracion |
| `GET /api/mesas/{id}` | todos | — | `Mesa` | — | mesas, sectores | salon |
| `PATCH /api/mesas/{id}` | **todos** | `{estado?, garzon_asignado_id?, reserva_id?, numero?, capacidad?, sector_id?}` | `Mesa` | estado ∈ {libre, ocupada, precuenta, bloqueada}; sin validar transiciones. `garzon_asignado_id` y `reserva_id` se actualizan si vienen presentes aunque sean `null`. **Cualquier rol puede cambiar cualquier campo** y liberar una mesa con pedido abierto (D4). | mesas | salon (operación) / administracion (estructura) |

### 2.4 Catálogo, cocina e inventario

| Método y ruta | Roles | Entrada | Salida | Reglas | Tablas | Destino |
|---|---|---|---|---|---|---|
| `GET /api/productos` | todos | — | `[Producto]` con modificadores | Incluye inactivos. Orden categoría, nombre. | productos, modificadores | salon (lectura), administracion |
| `POST /api/productos` | D/A | `{nombre, categoria, precio, cuarto_cocina_id, activo=true, descripcion?, modificadores:[{nombre, precio_adicional}]}` | 201 | Nombre no vacío; categoría ∈ {Entradas, Fondos, Bebidas, Postres}; precio ≥ 0; el cuarto existe; cada modificador con nombre y recargo ≥ 0. Producto y modificadores en una transacción. | productos, modificadores | administracion |
| `GET /api/productos/{id}` | todos | — | `Producto` | — | productos, modificadores | administracion |
| `PATCH /api/productos/{id}` | D/A | campos opcionales; `modificadores` reemplaza la lista entera | `Producto` | Igual que crear. Reemplazar modificadores = `DELETE` + `INSERT` (cambian los IDs). **Falla con 500 si algún modificador ya se vendió** (D14). | productos, modificadores | administracion |
| `GET /api/cuartos` | todos | — | `[Cuarto]` con impresora embebida | — | cuartos_cocina | administracion |
| `POST /api/cuartos` | D/A | `{nombre, descripcion, activo, impresora?: {nombre, direccion, puerto=9100, activa}}` | 201 | Nombre no vacío; impresora con nombre, dirección y puerto 1–65535. ID `cuarto_` + 12 hex generado en Python. | cuartos_cocina | administracion |
| `PATCH /api/cuartos/{id}` | D/A | cuerpo completo (semántica de PUT) | `Cuarto` | Igual que crear. | cuartos_cocina | administracion |
| `GET /api/materias-primas` | todos | — | `[MateriaPrima]` | — | materias_primas | administracion |
| `POST /api/materias-primas` | D/A | `{nombre, unidad_medida, stock_actual, stock_minimo, activo}` | 201 | unidad ∈ {kg, g, l, ml, unidad}; stock ≥ 0. **Cantidades decimales** (`NUMERIC(12,3)`). | materias_primas | administracion |
| `PATCH /api/materias-primas/{id}` | D/A | campos opcionales | `MateriaPrima` | Igual. | materias_primas | administracion |
| `GET /api/recetas` | todos | — | `[Receta]` | — | recetas, receta_ingredientes | administracion |
| `PUT /api/recetas` | D/A | `{producto_id, ingredientes:[{materia_prima_id, cantidad}]}` | `Receta` | Producto existe; al menos un ingrediente; cantidad > 0; materia prima existe; sin repetidos. Crea o reemplaza la receta completa. **No descuenta stock al vender.** | recetas, receta_ingredientes | administracion |
| `GET /api/configuracion` | todos | — | `{nombre_local, marca, propina_sugerida_pct, umbral_diferencia_pct, umbral_diferencia_minimo}` | Fila única. | configuracion_restaurante | administracion |
| `PATCH /api/configuracion` | D/A | campos opcionales | ídem | Nombre y marca no vacíos; propina 0–100; umbrales ≥ 0. `umbral_diferencia_pct` es **decimal** (`NUMERIC(5,2)`). | configuracion_restaurante | administracion |

### 2.5 Pedidos (comandas)

| Método y ruta | Roles | Entrada | Salida | Reglas | Tablas | Destino |
|---|---|---|---|---|---|---|
| `GET /api/pedidos?mesa_id&estado` | todos | filtros opcionales | `[Pedido]` con ítems | Orden por creación descendente. Una consulta de ítems por pedido (N+1). | pedidos, items_comanda, productos, modificadores | pedidos |
| `POST /api/pedidos` | todos | `{mesa_id}` | 201 `Pedido` | Mesa existe. Si la mesa tiene un pedido en `abierto` o `precuenta`, lo devuelve; si no, crea uno con el garzón actual y **ocupa la mesa solo si estaba libre** (`garzon_asignado_id` se conserva si ya tenía uno). Responde 201 también cuando devuelve uno existente. **No es atómico** (D5). | pedidos, mesas | pedidos |
| `GET /api/pedidos/{id}` | todos | — | `Pedido` | 404 si no existe. | ídem | pedidos |
| `POST /api/pedidos/{id}/items` | todos | `{producto_id, cantidad=1, modificador_id?, observacion_libre?}` | 201 `ItemComanda` | cantidad > 0; pedido existe (**no valida su estado**, D1); producto existe y activo; el modificador pertenece al producto. `precio_unitario` = precio + recargo, **congelado** al agregar. Nace en `en_espera`. | items_comanda | pedidos |
| `PATCH /api/pedidos/{id}/items/{item}` | todos | `{cantidad?, estado?, observacion_libre?}` | `ItemComanda` | cantidad > 0; estado ∈ {en_espera, enviado}; al menos un campo. **No valida el estado actual**: se puede bajar la cantidad de un ítem enviado o devolverlo a `en_espera` y luego borrarlo, sin autorización (D3). | items_comanda | pedidos |
| `DELETE /api/pedidos/{id}/items/{item}` | todos | — | 204 | Solo si el ítem está `en_espera`; si no, 404 "Item no encontrado o ya fue enviado". | items_comanda | pedidos |
| `POST /api/pedidos/{id}/enviar` | todos | — | `[ItemComanda]` (todos) | Pasa **todos** los ítems `en_espera` del pedido a `enviado`. No crea una entidad de tanda, no guarda la hora de envío, no imprime. | items_comanda | pedidos |
| `POST /api/pedidos/{id}/precuenta` | todos | — | `Mesa` | Pedido → `precuenta`, mesa → `precuenta`. **No valida estados**: reabre un pedido cerrado (D2). No imprime. | pedidos, mesas | pedidos |
| `POST /api/pedidos/{id}/finalizar` | D/A/C | — | `Pedido` | Exige Σ pagos ≥ Σ (precio × cantidad). Pedido → `cerrado` con hora; mesa → `libre` y sin garzón. No exige que el pedido esté en precuenta ni que exista un documento. | pedidos, pagos, mesas | caja (`venta.cerrada`) |

### 2.6 Pagos y caja

| Método y ruta | Roles | Entrada | Salida | Reglas | Tablas | Destino |
|---|---|---|---|---|---|---|
| `GET /api/pagos?pedido_id\|mesa_id` | todos | uno de los dos | `[Pago]` con ítems cobrados | 400 si no viene ninguno. | pagos, pago_items | caja |
| `POST /api/pagos` | D/A/C | ver §3.3 | 201 `Pago` | Exige turno abierto. Valida método, monto, código de tarjeta, tipos y saldo (§3.3). Pago + ítems cobrados + evento outbox en **una transacción**. La lectura del saldo y la escritura **no son atómicas** (D6). | pagos, pago_items, eventos_salida, turnos_caja, pedidos, items_comanda | caja |
| `POST /api/caja/turnos` | D/A/C | `{monto_apertura=0}` | 201 `Turno` | monto ≥ 0. Solo un turno abierto (validación + índice único parcial en BD). | turnos_caja | caja |
| `GET /api/caja/turnos/actual` | D/A/C | — | `Turno` | 404 si no hay turno abierto. | turnos_caja | caja |
| `POST /api/caja/turnos/{id}/conteo-efectivo` | D/A/C | `{monto}` | `{turno, requiere_segundo_conteo, conteo_completado}` | Arqueo ciego (§3.4). | turnos_caja, pagos, retiros_caja, configuracion_restaurante | caja |
| `POST /api/caja/turnos/{id}/conciliacion-terminal` | D/A/C | `{total_debito_pos, total_credito_pos, total_notas_credito_pos=0}` | `Turno` | Valores ≥ 0; turno abierto. Se puede sobrescribir sin límite (D17). | turnos_caja | caja |
| `POST /api/caja/turnos/{id}/cerrar` | D/A/C | — | `ResultadoCierre` | Exige primer conteo, segundo si se pidió, y conciliación. Calcula esperado, diferencia y totales por medio (§3.4). No pide autorización si descuadra ni marca el cierre como observado (D18). | turnos_caja, pagos, retiros_caja | caja |
| `POST /api/caja/retiros` | D/A/C | `{monto, motivo, codigo_autorizacion}` | 201 `Retiro` | monto > 0; motivo no vacío; turno abierto; el código debe calzar con el PIN de **algún** dueño o admin activo (D13). Código inválido → **401**, y el frontend, al recibir 401, **cierra la sesión del cajero** (D12). | retiros_caja, usuarios, turnos_caja | caja |
| `GET /api/caja/retiros?turno_id` | D/A/C | opcional; si falta usa el turno abierto | `[Retiro]` descendente | — | retiros_caja | caja |

### 2.7 Nube v1 (nodo híbrido) — se elimina completo

| Método y ruta | Roles | Qué hace |
|---|---|---|
| `GET /api/cloud/estado` | todos | Estado del enrolamiento y eventos pendientes del outbox |
| `POST /api/cloud/enrolar` | D/A | Genera un par Ed25519, lo registra en `fleet-enroll` con el ID token de Google del admin y guarda la clave privada en Postgres |

Funciones de `aws-upload/lambdas/` (desplegadas en la API `mise-pos-api`): `auth-google-start`,
`auth-google-callback`, `node-authorizer`, `users-me`, `reports-dashboard`, `config-catalog`,
`fleet-enroll`, `ingest`, `config-pull`, `fleet-heartbeat`. Ninguna se reutiliza tal cual. De
`ingest` y `reports-dashboard` se rescata la idea de deduplicar por ULID y de agregados por fecha.

---

## 3. Lógica de negocio: dónde vive

### 3.1 Backend

| Regla | Dónde | ¿Pura? | Nota para la migración |
|---|---|---|---|
| Validaciones de entrada de cada caso de uso | `use_cases/*.py` | Sí | Se mueve casi tal cual a `pos_dominio` |
| Precio congelado = precio + recargo | `AgregarItemUseCase` | Sí | — |
| Saldo, sobrepago y unidades por ítem ya cobradas | `RegistrarPagoUseCase` | Sí, con datos leídos | En DynamoDB la lectura y la escritura deben quedar bajo condición |
| Totales del turno, esperado, umbral, segundo conteo | `caja_use_cases.py` | Sí | `calcular_umbral_diferencia` usa `round()` de Python (D11) |
| Solo se borran ítems en espera | **SQL** `delete_item_en_espera` | No | Subir al dominio como condición |
| Enviar tanda = todos los en espera | **SQL** `enviar_tanda` | No | Subir al dominio |
| Ocupar mesa solo si está libre; conservar garzón | **SQL** `ocupar_si_libre` (`COALESCE`) | No | Subir al dominio |
| Liberar mesa borra el garzón | **SQL** `liberar` | No | Subir al dominio |
| Pedido abierto de la mesa = el más reciente en abierto o precuenta | **SQL** `find_abierto_by_mesa` | No | En DynamoDB: puntero en el ítem de la mesa |
| Un solo turno abierto | **índice único parcial** | No | Condición `attribute_not_exists` sobre un ítem de turno abierto |
| Autorizador = dueño o admin activo con PIN que calce | `usuario_repository.find_autorizador_por_pin` + `security.verify_pin` | No | Subir al dominio; ver P8 |
| Usuario con historial no se borra | **SQL** `tiene_historial` (4 `EXISTS`) | No | Caro en DynamoDB; ver P15 |
| Prefijos de ID (`usr_`, `m_`, `ped_`, `item_`, `pago_`, `turno_`, `retiro_`, `prod_`, `mod_`, `mp_`, `rec_`, `res_`, `sector_`, `cuarto_`) | defaults de Postgres y `cuartos_use_cases` | — | Pasan a generarse en el dominio |
| Hora de los hechos | `now()` de Postgres | — | Pasa a la hora de Lambda (UTC) |

### 3.2 Frontend (no existe en el backend)

| Regla | Dónde | Comportamiento exacto |
|---|---|---|
| Total del pedido | `PendientesCaja.calcularTotalPedido` | Σ precio_unitario × cantidad |
| Saldo pendiente | `PendientesCaja` | máx(total − Σ montos pagados, 0). Las propinas no cuentan |
| **División por ítems** | `PendientesCaja.cobrarSeleccionItems`, `DivisionPorItems` | Por ítem, cantidad = mín(seleccionada, cantidad − ya cobrada), descartando ≤ 0. Monto = **mín(Σ precio × cantidad, saldo pendiente)** |
| **División en partes iguales** | `PendientesCaja.crearDivisionIgual`, `DivisionPartesIguales` | Entre 2 y 20 personas, sobre el **saldo pendiente**. Base = ⌊saldo / n⌋; el resto (saldo mod n) se reparte de a $1 a las **primeras** partes. Qué partes se pagaron vive **solo en memoria** del navegador |
| **División por monto libre** | `PendientesCaja.cobrarMontoLibre`, `MontoLibre` | Entero entre 1 y el saldo pendiente |
| **Propina sugerida** | `PendientesCaja.prepararPropina` | round_half_up(monto_a_cobrar × pct / 100) con `Math.round`, donde el monto es **lo que se cobra en ese paso** (saldo, parte o selección), no el total de la cuenta. `pct` viene de la configuración (10 si falla la carga) |
| Botón "usar propina sugerida" | `FormularioPago.usarPropinaSugerida` | **10 % fijo**, ignora la configuración (D10) |
| **Pago mixto** | `FormularioPago` | Sin modo mixto: un medio cubre todo. En mixto: cada medio indica su monto y **el último cubre automáticamente el resto**; la suma debe ser exacta. La **propina completa va al último medio**. Tarjeta exige código del terminal. Efectivo recibido ≥ monto + propina de ese medio |
| Registro del pago mixto | `PendientesCaja.confirmarPago` | Un `POST /api/pagos` **por medio, en secuencia y sin atomicidad** (D9). Solo el primero lleva `items_cobrados`. `tipo_division` por defecto `completa` |
| Datos que no se envían | `PendientesCaja.confirmarPago` | `efectivo_recibido`, `vuelto`, `tipo_documento` y `datos_facturacion` **nunca se mandan**: quedan `null` en la base (D8) |
| Documento tributario | `SeleccionDocumento`, `DatosFactura`, `DocumentoTributario` | Se elige **después** de pagar todo; la vista es simulada (`simularImpresion`); luego se llama a `finalizar` |
| Arqueo ciego | `CierreCaja` | No muestra el esperado hasta el cierre |
| Ítems en espera | `OrderPage`, `ComandaMesa` | Todo ítem nuevo queda "En espera" hasta pulsar enviar, que manda **todos** los que esperan. No hay forma de retener algunos y enviar otros |
| Pantalla de inicio por rol | `auth.service.getHomeRoute` | dueño/admin → `/dashboard`, cajero → `/caja`, garzón → `/pos/tables`, cocina → `/menu` |
| Guardas por rol | `router.tsx` + `RequireAuth` | Solo ocultan pantallas; el backend aplica sus propias reglas (§2) |

### 3.3 Validaciones de `POST /api/pagos`, en orden

1. Hay turno abierto (si no, 400).
2. `metodo` ∈ {efectivo, debito, credito, transferencia}.
3. `monto` > 0.
4. Débito o crédito exige `codigo_autorizacion_pos`.
5. `tipo_division` ∈ {completa, items, partes_iguales, monto_libre} o `null`.
6. `tipo_documento` ∈ {boleta, factura} o `null`.
7. Si trae `pedido_id`: el pedido existe; `monto` ≤ total − Σ montos previos; cada ítem cobrado pertenece al pedido y su cantidad ≤ cantidad − ya cobrada.
8. Si **no** trae `pedido_id`: no se valida saldo (D7).
9. La propina no tiene validación de rango.

### 3.4 Arqueo y cierre

- **Esperado** = apertura + Σ(monto + propina) de pagos en efectivo del turno − Σ retiros.
- **Umbral** = máx(`round(esperado × pct / 100)`, mínimo). Por defecto 2 % y $5.000.
- **Primer conteo**: si |conteo − esperado| > umbral, marca `requiere_segundo_conteo` y responde
  `conteo_completado=false`. La diferencia no se revela.
- **Segundo conteo**: se acepta siempre y es el **definitivo**, aunque siga fuera del umbral.
- **Cierre**: exige conteos y conciliación. Responde esperado, conteo definitivo, diferencia
  (conteo − esperado) y totales de débito, crédito y efectivo **incluyendo propina**.

---

## 4. Datos

### 4.1 Tablas y destino tentativo

| Tabla Postgres | Contenido | Destino tentativo |
|---|---|---|
| `usuarios` | personal, rol, PIN | `configuracion` |
| `sectores` | sectores del salón | `configuracion` |
| `mesas` | estructura **y** estado operativo | estructura en `configuracion`, estado en `operacion` (a decidir en Fase 1) |
| `reservas` | reservas (sin endpoints) | `operacion` |
| `cuartos_cocina` | estaciones con impresora embebida (IP y puerto) | `configuracion` (impresora pasa a ítem propio con clave) |
| `productos`, `modificadores` | catálogo | `configuracion` |
| `materias_primas`, `recetas`, `receta_ingredientes` | inventario | `configuracion` (ver P11) |
| `configuracion_restaurante` | fila única con parámetros | `configuracion`, por local |
| `pedidos`, `items_comanda` | comandas | `operacion` |
| `turnos_caja`, `retiros_caja` | caja | `operacion` |
| `pagos`, `pago_items` | cobros | `operacion` |
| `eventos_salida` | outbox hacia la nube | **se elimina** (lo reemplaza `EVT#` + Streams) |
| `nodo_cloud` | identidad del nodo | **se elimina** |

### 4.2 Consultas con JOIN o agregación

| Consulta | Dónde | Cómo resolverla sin JOIN |
|---|---|---|
| Ítems con producto y modificador embebidos (`row_to_json`) | `pedido_repository._SELECT_ITEMS` | Copiar nombre, categoría y cuarto en el ítem al agregarlo (ya se congela el precio) |
| Mesas con nombre de sector | `mesa_repository._SELECT_MESA` | Copiar el nombre del sector en la mesa, o unir en memoria (pocos sectores) |
| Pedidos con sus ítems (N+1) | `list_by_filters` | Pedido e ítems bajo la misma clave de partición: una sola `Query` |
| Productos con modificadores | `producto_repository.list_all` | Modificadores dentro del ítem del producto |
| Σ pagos por pedido y unidades cobradas por ítem | `RegistrarPagoUseCase`, `FinalizarCuentaUseCase` | Acumulados en el ítem del pedido, actualizados con condición en la misma transacción |
| Σ pagos y retiros del turno | `caja_use_cases` | Agregados del turno; el cierre debe leer la fuente, no un agregado asíncrono (P-riesgo en Fase 1) |
| Usuario con historial (4 `EXISTS`) | `tiene_historial` | Ver P15 |
| Autorizador por PIN (recorre todos los admins) | `find_autorizador_por_pin` | Ver P8 |
| Conteo de eventos pendientes | `evento_salida_repository` | Se elimina |

### 4.3 Transacciones

**Atómicas hoy** (una transacción de Postgres):

- Pago + ítems cobrados + evento `pago.registrado` en el outbox.
- Producto + reemplazo de modificadores.
- Receta + reemplazo de ingredientes.

**Secuencias no atómicas** (cada paso es su propia transacción): crear pedido + ocupar mesa;
precuenta del pedido + de la mesa; finalizar (leer + cerrar pedido + liberar mesa); pagar (leer saldo +
insertar); primer conteo + marcar segundo conteo; cerrar turno (leer + cerrar); eliminar usuario (leer
historial + borrar). En la nube cada una debe ser una sola `TransactWriteItems` con condiciones.

### 4.4 Secuencias, correlativos y folios

- **No hay ninguno.** Todos los IDs son UUID con prefijo. El único serial es `eventos_salida.id`, que
  se elimina.
- El requisito RF-C01 ("correlativo único de documentos por local") **no está implementado**. Los
  folios de boleta y factura serán nuevos (contador atómico por cliente y tipo).
- No existe número visible de pedido ni de comanda.

### 4.5 Tipos numéricos

- Todos los montos son `INTEGER` en pesos. Bien.
- **No son enteros**: `configuracion_restaurante.umbral_diferencia_pct` (`NUMERIC(5,2)`, se lee como
  `float`), `materias_primas.stock_actual` y `stock_minimo` y `receta_ingredientes.cantidad`
  (`NUMERIC(12,3)`). boto3 rechaza `float`; hay que guardarlos como `Decimal` o como enteros en una
  unidad menor (puntos base, gramos, mililitros). Se decide en la Fase 1.

### 4.6 Datos semilla

`02_seed.sql` crea usuarios, sectores, mesas, reservas, cuartos, productos con modificadores,
materias primas, recetas, dos pedidos con ítems y un pago. Habrá que traducirlo a ítems de DynamoDB.
**El primer dueño debe crearse a mano en la consola de DynamoDB**, porque sin él nadie puede llamar a
la API de administración.

---

## 5. Dependencias externas y su reemplazo

| Hoy | Uso | Reemplazo |
|---|---|---|
| PostgreSQL 16 + psycopg2 | persistencia | DynamoDB (`configuracion`, `operacion`) con boto3 |
| FastAPI + uvicorn | HTTP | API Gateway HTTP API + manejador Lambda que despacha por `routeKey` |
| Pydantic | esquemas y validación | dataclasses con validación explícita |
| PyJWT (HS256) | `device_token` propio | **Nada**: el autorizador JWT valida el ID token de Google |
| PyJWT `PyJWKClient` | verificar el ID token contra el JWKS | Autorizador JWT del API Gateway |
| cryptography (Ed25519) | identidad del nodo | **Se elimina** |
| python-dotenv | configuración | Variables de entorno de Lambda |
| nginx (proxy + estático) | servir la SPA y `/api` | S3 con su endpoint HTTPS (C1: CloudFront no disponible) |
| Broker OAuth (`auth-google-*`) + Secrets Manager (`mise/google-oauth`) | flujo de código de Google | Google Identity Services en el navegador; **no requiere secreto de cliente** |
| `node-authorizer` + capa `pyjwt-arm64` | autorizar nodos | **Se elimina** |
| Impresoras térmicas por IP:9100 | solo modeladas, nunca usadas | Impresoras con impresión desde la nube (p. ej. CloudPRNT) consultando a `impresion` |
| Proveedor de documentos tributarios | no existe | Puerto `EmisorDTE` con proveedor simulado |
| Plataformas de delivery | no existe | Webhook `pedidos-externos` con firma HMAC |
| Terminal bancario | manual: el cajero digita código y totales | Sin cambio |
| Frontend: React 19, react-router 7, Vite 8, Tailwind 4 | — | Se mantienen. **No hay manifiesto ni service worker**: la "PWA" no existe todavía |

---

## 6. Estado en memoria, hilos y procesos periódicos

| Comportamiento | Dónde | En Lambda |
|---|---|---|
| Tarea `sync_loop` cada 30 s que vacía el outbox hacia la nube | `main.py` (lifespan) + `node_sync.py` | Desaparece: DynamoDB Streams → `procesador-eventos` |
| Pool de conexiones a Postgres (1–10) | `db.py` | Cliente boto3 creado al cargar el módulo |
| Caché del JWKS de Google | `security._google_jwk_client` | Lo hace el autorizador JWT |
| Repositorios como instancias únicas | `deps.py` | Sin estado; se crean al cargar el módulo |
| `Settings` leídos al importar | `config.py` | Variables de entorno leídas al cargar |
| Sesión, ID token y `device_id` en `localStorage` | `auth.service.ts` | **Prohibido**: el token vive solo en memoria |
| Partes iguales ya cobradas | `PendientesCaja` (estado de React) | Sigue en memoria salvo que se decida persistir (P10) |
| `propinaSugeridaPct` cargado una vez | `PendientesCaja` | Igual |
| Plano de mesas cargado una sola vez, **sin refresco** | `TablesPage` | Con varios dispositivos hace falta refrescar (P19) |
| Procesos programados | **ninguno** en local | `tareas-programadas` es nueva y sin especificación (P14) |

---

## 7. Comportamientos que se pierden o cambian en la nube

| # | Cambio | Efecto en el usuario |
|---|---|---|
| 1 | Sin internet en el local no se vende. Hoy el nodo local funciona sin internet | Garzones ven «Sin conexión: usa la caja»; solo el PC de caja encola |
| 2 | ID token de Google de ~1 h con renovación silenciosa, en vez de `device_token` de 12 h | Si la renovación falla, aparece «Ingresar» sin perder la comanda |
| 3 | Token solo en memoria | Recargar la página exige volver a ingresar (silencioso en celulares; en caja, con selección manual de cuenta) |
| 4 | Errores `{codigo, mensaje, requestId}` y rechazos de negocio como 409/422 en vez de 400 | Hay que adaptar `apiError.ts`; los mensajes se mantienen |
| 5 | Latencia a `us-east-1` (~150–250 ms desde Chile) más arranques en frío | Cada acción tarda más que en la red local |
| 6 | Idempotencia por `X-Command-Id` | Reintentar ya no duplica pagos ni ítems |
| 7 | Contingencia de comandas | Nuevos mensajes: «aceptada en contingencia», «registrada, no impresa», bandeja de conflictos |
| 8 | Impresión real en cocina desde la nube | Requiere impresoras compatibles; la configuración IP/puerto deja de servir y pasa a una clave por impresora |
| 9 | Documentos tributarios con folio, emitidos después del cobro | La caja ve el estado del documento y puede reimprimir |
| 10 | Reportes del turno desde agregados asíncronos | Unos segundos de retraso respecto de la venta |
| 11 | Código de autorización con bloqueo tras 5 intentos | Nuevo; hoy no hay límite |
| 12 | Código inválido en un retiro | Ya no cierra la sesión del cajero (D12) |
| 13 | Usuario desactivado | Pierde acceso en ≤ 60 s; hoy conserva su sesión hasta 12 h |
| 14 | Matriz de roles aplicada en el servidor | Acciones que hoy cualquier rol puede hacer (D4, D16) quedarán restringidas |
| 15 | Hora en UTC en vez de la del contenedor de Postgres | Fechas de turno y particiones deben calcularse en hora de Chile (riesgo R3) |
| 16 | CORS con origen exacto en vez de `*` | Solo la URL publicada del sitio puede usar la API |
| 17 | IDs nuevos (ULID) | Los datos de Postgres no se migran salvo que se pida (P15) |

---

## 8. Contradicciones con las decisiones cerradas

No se cambia ninguna decisión. Se reportan para que el equipo decida.

| # | Contradicción | Evidencia | Consecuencia |
|---|---|---|---|
| **C1** | **CloudFront denegado** en el Learner Lab | `aws/ESTADO.md` §6.1: el rol `voclabs` deniega todas las operaciones de CloudFront, incluso `ListDistributions` y `CreateOriginAccessControl`. El panel v1 se publicó con alojamiento web de S3 por **HTTP** | Por HTTP: (a) **no hay service worker** (exige contexto seguro), así que no hay PWA ni actualización controlada; (b) Google Identity Services solo acepta orígenes **HTTPS** (salvo `localhost`), así que **el inicio de sesión decidido no funciona**; (c) el bucket debe ser público. Opciones en P1 |
| C2 | El código es la arquitectura híbrida con nodo local (Postgres, outbox, sincronización cada 30 s). Los requisitos también la asumen: RF-S02 "verificación local, sin dependencia de la nube", respaldo de energía "para los nodos", sincronización cada minuto | `node_sync.py`, `eventos_salida`, `nodo_cloud`, requisitos líneas 186, 324, 352 | Se elimina: `/api/cloud/*`, `node_sync.py`, tablas `eventos_salida` y `nodo_cloud`, y las 10 funciones de `aws-upload/` |
| C3 | Tokens propios: `pos-api` firma un `device_token` HS256; el nodo firma `node_jwt` EdDSA con la capa `pyjwt[crypto]` | `security.issue_token`, `node_sync.construir_node_jwt` | Se eliminan; solo se usa el ID token de Google |
| C4 | Secreto de cliente de Google en Secrets Manager para el broker OAuth | `ESTADO.md` §3.2 y §5.3: el secreto **se compartió por chat y sigue sin rotar** | El login sigue siendo OAuth 2.0 + OpenID Connect con Google, pero con el flujo para aplicaciones de navegador, que entrega el ID token directo y no usa secreto. **Decisión del equipo (2026-10-14): el secreto se deja como está por ahora**; la v2 no lo lee |
| C5 | Ya existe una tabla `configuracion` con otro esquema (GSI `por_email`, claves `USER#<id>` sin cliente en la partición) y una tabla `eventos` con TTL de 13 meses en `ttl_timestamp` | `aws-upload/tables.sh`, `seed.sh` | Choque de nombre con la nueva `configuracion`. Ver P20 |
| C6 | La API v1 usa stage `$default` con despliegue automático | `ESTADO.md` §3.5 | La nueva `pos-api` usa stage `prod` sin despliegue automático; conviven sin conflicto si los nombres difieren |
| C7 | La guía del curso pedía CDK/CloudFormation y Powertools | `ESTADO.md` §5 y §6.2 | Prevalece la decisión cerrada: consola, sin IaC, solo biblioteca estándar y boto3 |
| C8 | Ruteo de impresión: el requisito dice "según la **categoría** del producto"; el código asigna cuarto **por producto** (`productos.cuarto_cocina_id`) | requisitos líneas 231–232; `01_schema.sql` | No es decisión cerrada, pero hay que elegir uno (P16) |
| C9 | Stock y cantidades de receta en decimal | `NUMERIC(12,3)` | La regla de enteros es para montos, pero boto3 rechaza `float` igual (§4.5) |

---

## 9. Reglas que el prompt pide caracterizar y que no existen en el código

| Regla pedida | Estado en el código local | ¿Se puede caracterizar? |
|---|---|---|
| Comanda por tandas | Existe: enviar = todos los ítems en espera; sin entidad de tanda ni hora de envío | Sí |
| Ítems en espera | Existe solo como borrador hasta enviar; no se pueden retener unos y enviar otros (el requisito RF habla de "liberación posterior") | Sí, el comportamiento actual |
| **Anulación con código** | **No existe**. Solo hay código para retiros. El enum de pedido tiene `anulado`, pero ninguna ruta lo usa | **No** |
| División de cuenta (ítems, partes iguales, monto libre) | Existe, en el frontend | Sí, desde el TypeScript |
| Pagos mixtos | Existe, en el frontend + validación de saldo en el backend | Sí |
| **Propina sobre el total antes de descuentos** | **No hay descuentos**. La propina se sugiere sobre el monto que se cobra en cada paso | Solo la parte de la propina |
| Arqueo ciego con recuento sobre el umbral | Existe | Sí |

Otros requisitos sin implementación local: reservas (tabla y semilla, sin rutas ni pantallas),
impresión de comandas, precuenta y documento (RF-C02, RF-C04), documentos tributarios y folios
(RF-C01), propinas por garzón en el cierre (RF-C09), cierre observado (RF-C13), autorización del cierre
descuadrado (RF-C15), acciones de administrador con código (RF-S01: anular ítem, aplicar descuento,
reabrir mesa cerrada, autorizar cierre, trasladar ítems), pedidos de plataformas, reportes.

---

## 10. Defectos y comportamientos dudosos del código local

La regla es no cambiar comportamiento sin una prueba que lo documente. Para cada uno se propone qué
hacer; ninguno se aplica sin confirmación (P4).

| # | Hoy | Propuesta |
|---|---|---|
| D1 | Se pueden agregar ítems a un pedido en precuenta o cerrado | Solo en `abierto` (¿y en precuenta, volviéndolo a abierto?) |
| D2 | Precuenta no valida estado: reabre un pedido cerrado | Solo desde `abierto` |
| D3 | PATCH de ítem permite bajar la cantidad de un ítem enviado o devolverlo a espera y borrarlo, sin autorización | Ítem enviado inmutable; quitarlo = anulación con código |
| D4 | Cualquier rol cambia cualquier campo de una mesa y puede liberar una mesa con pedido abierto | Estructura solo D/A; estado operativo solo por los casos de uso |
| D5 | Crear pedido no es atómico: dos garzones pueden abrir dos pedidos en la misma mesa. Una mesa bloqueada recibe pedido y sigue bloqueada | Condición sobre la mesa; rechazar si está bloqueada |
| D6 | Pago no atómico: dos cobros simultáneos pueden superar el total | Condición sobre el saldo en la misma transacción |
| D7 | Pago sin `pedido_id` no valida saldo | Exigir `pedido_id` |
| D8 | `efectivo_recibido`, `vuelto`, `tipo_documento` y datos de facturación nunca llegan al backend | Enviarlos; el documento al finalizar (P9) |
| D9 | Pago mixto = varios POST sin atomicidad: si falla el segundo, el primero queda | Un comando con N medios (P10) |
| D10 | "Usar propina sugerida" usa 10 % fijo | Usar la configuración |
| D11 | Redondeo: el frontend usa `Math.round` (mitad hacia arriba); el umbral del backend usa `round` de Python (mitad al par). Ej.: esperado $250.025 al 2 % → 5000,5 → Python 5000, JS 5001 | Mantener cada uno como está y fijarlo en pruebas; al mover la propina al dominio, usar mitad hacia arriba explícita |
| D12 | Código inválido en un retiro → 401 → el frontend cierra la sesión | 403 o 422; nunca 401 |
| D13 | El código no identifica a nadie: se prueba contra todos los admins (N × PBKDF2); dos admins con el mismo PIN, gana el primero | Ver P8 |
| D14 | Editar modificadores de un producto ya vendido con modificador → 500 por llave foránea | Modificadores con ID estable; los ítems guardan copia |
| D15 | Duplicados (mesa por sector y número, nombre de sector o cuarto) → 500 | 409 |
| D16 | Un admin puede crear dueños o ascenderse a dueño | Solo un dueño crea o asciende dueños |
| D17 | La conciliación del terminal se puede sobrescribir sin límite | Mantener (es corrección de digitación) o bloquear tras el cierre |
| D18 | Cierre descuadrado sin autorización ni estado "observado" (exigidos por RF-C13 y RF-C15) | Implementar si entra en alcance (P3) |
| D19 | `/api/health` no verifica la base | `/salud` sí verifica DynamoDB |
| D20 | El plano de mesas no se refresca | Refresco periódico (P19) |
| D21 | `/api/auth/login` crea cuentas con cualquier email sin verificación | Se elimina |
| D22 | (frontend) Partes iguales con más personas que pesos crea partes de $0 que no se pueden cobrar | Rechazar (`PARTE_EN_CERO`) |
| D23 | Un mismo ítem repetido en la selección se valida por separado: se cobran 4 unidades de un ítem de 3 (frontend y backend) | Sumar antes de validar |
| D24 | (frontend) La vista previa de la división por ítems usa el precio actual del catálogo; el cobro usa el precio congelado | El servidor usa siempre el congelado |

D22–D24 se encontraron en la Fase 2 al caracterizar el frontend. Estado de cada uno: `caracterizacion.md`.

---

## 11. Preguntas abiertas

**Bloqueantes para la Fase 1**

- **P1. Sitio sin CloudFront (C1).** Resuelta: CloudFront no se usará nunca en este entorno. El sitio
  va en **S3 por su endpoint REST con HTTPS**: sirve para Google Identity Services y el service
  worker; exige bucket público de solo lectura, enrutador con `#` y control de caché con
  `Cache-Control` por archivo (no hay invalidación que hacer).
- **P2. Línea base.** `POS/POS` tiene 24 archivos modificados y 16 rutas nuevas sin commitear, y el submódulo `mise-frontend` otras 64
  (su remoto es `github.com/achavezs16/mise-frontend`, de otro integrante). ¿Commitean ustedes ese
  trabajo antes de que cree `feature/migracion-lambdas` en ambos repositorios? Aviso aparte: tu
  carpeta de usuario `C:\Users\hpvic` es en sí un repositorio git (con archivos borrados en el
  índice). No lo toqué.
- **P3. Alcance de lo no implementado (§9).** ¿Se implementan en esta migración la anulación con
  código, los descuentos, reabrir mesa, trasladar ítems, el cierre observado y autorizado, las
  propinas por garzón y las reservas? Si entran, necesito las reglas: qué se anula (ítem, pedido),
  motivo obligatorio, si la anulación avisa a cocina, tipo de descuento (porcentaje o monto, por
  ítem o por cuenta) y quién lo aplica.
- **P6. Identidad y clientes.** El alta es por email antes del primer ingreso, pero la clave decidida
  es `USER#sub`, y el `sub` se conoce recién al ingresar. Propuesta: el alta crea una invitación por
  email y el primer ingreso la vincula al `sub`. ¿Una persona pertenece a un solo cliente? ¿El rol es
  por cliente o por local? ¿Un garzón puede trabajar en dos locales?
- **P7. Jerarquía cliente → marca → local.** Hoy la configuración es una fila única con `nombre_local`
  y `marca`. ¿El catálogo es por marca o por local? ¿Propina y umbrales son por local?
- **P9. Documento tributario.** Hoy se elige después de pagar y no se envía. Propuesta: `finalizar`
  recibe `tipo_documento` y los datos del receptor, y eso viaja en `venta.cerrada`. ¿De acuerdo?

**Necesarias antes de la Fase 2**

- **P4.** ¿Se corrigen D1–D21 como se propone (cada corrección con su prueba) o se replica el
  comportamiento actual?
- **P5.** Matriz de roles: la propondré por ruta en `02-api-gateway.md`. ¿El rol `cocina` sigue sin
  pantalla?
- **P8. Código de autorización.** ¿Se mantiene "solo el código" (el servidor prueba contra todos los
  admins) o el autorizador elige su nombre y digita su código (un solo cálculo, y el bloqueo de 5
  intentos queda por autorizador)? Lo segundo es más seguro y barato, pero cambia la pantalla.
- **P10.** ¿El pago mixto pasa a ser un solo comando con N medios (atómico)? ¿Se persiste la división
  en partes iguales?
- **P11.** ¿El inventario va en `administracion`? ¿Las cantidades se guardan como enteros en unidad
  menor (g, ml, unidad) o como decimales?
- **P12.** Reglas de reservas (duración, anticipación, capacidad, horario): no existen en el código.
- **P13.** Pedidos externos: ¿qué plataforma y qué formato? No hay concepto de pedido sin mesa.
- **P14.** `tareas-programadas`: ¿qué tareas? (por ejemplo: aviso de turno abierto hace más de N
  horas, expiración de reservas, reintento de documentos atascados).
- **P15.** ¿Se migran datos desde Postgres o se parte con datos semilla? ¿Se mantiene "desactivar en
  vez de borrar" para usuarios con historial, o se archiva siempre?
- **P16.** Impresoras: ¿modelo concreto con CloudPRNT? ¿La caja tiene su propia impresora (hoy solo
  existen impresoras por cuarto)? ¿Ruteo por categoría o por producto (C8)?
- **P19.** ¿Refresco del plano de mesas cada cuánto? Cada consulta cuesta lecturas.
- **P20.** Recursos existentes en AWS (`mise-pos-api`, tablas `configuracion` y `eventos`, 10
  funciones, capa, secreto, bucket del panel): ¿se borran antes de empezar? La tabla `configuracion`
  choca de nombre.
- **P22.** Correos de suscripción a los temas SNS del dueño y de alertas técnicas (cada uno debe
  confirmar el correo de AWS).

---

## 12. Riesgos detectados en esta fase

| # | Riesgo | Mitigación propuesta |
|---|---|---|
| R1 | C1: sin HTTPS no hay PWA ni GIS | Resuelto: S3 con su endpoint HTTPS |
| R2 | Pruebas de caracterización del frontend: la lógica está en TypeScript y no hay framework de pruebas | Ejecutar las funciones actuales con Node 22 (instalado) para obtener los valores esperados y fijarlos en pytest |
| R3 | Zona horaria `America/Santiago` en Lambda: `zoneinfo` necesita la base tz del sistema y no está garantizada en el runtime de Python 3.12 | Probarlo con una función mínima el primer día; si falla, calcular la fecha operativa desde la apertura del turno |
| R4 | Entorno local: Python 3.11 y 3.13 instalados, no 3.12; sin Docker en el PATH | Escribir código compatible con 3.11–3.13 y probar con 3.13; moto no necesita Docker |
| R5 | PBKDF2 de 200 000 iteraciones por admin en Lambda con poca memoria (poca CPU) | Resolver P8; dar 512 MB a `caja` |
| R6 | Agregados asíncronos usados para el cierre de turno darían cifras atrasadas | El cierre lee los pagos del turno directamente (consulta consistente) |
| R7 | Secreto de Google comprometido (C4) | La v2 no lo usa. El equipo decidió no rotarlo por ahora; rotarlo si alguna vez se vuelve al flujo con código de autorización |
