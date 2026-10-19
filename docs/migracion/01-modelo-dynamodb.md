# 01 — Modelo de datos en DynamoDB

Fase 1 de la migración. Define las claves de las dos tablas, qué consulta cada pantalla y función, y
qué escribe cada operación crítica y con qué condición. **Es la decisión más difícil de cambiar
después**: revisarla antes de escribir código (punto de control 2).

Alcance: las funciones que ya existen en el POS local más los mecanismos de plataforma que exige la
migración (decisión P3 de `00-inventario.md`). Reservas y pedidos externos quedan fuera; sus prefijos
de clave se reservan en §4.4 para que no choquen después.

---

## 0. Decisiones de diseño a revisar

| # | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|
| M1 | Cada ruta de negocio lleva el local: `/locales/{local_id}/...`. **El cliente y el rol se leen de la membresía en `configuracion`**; el `local_id` de la ruta solo dice cuál membresía usar, y si no existe se responde 403 | El dueño tiene varios locales y debe poder elegir. El rol nunca sale de la petición ni del token | "Local activo" guardado por usuario: falla con el dueño abriendo dos locales en dos pestañas |
| M2 | Una persona = una cuenta de Google (`sub`). Tiene **una membresía por local** con su rol. Un admin en dos locales = dos membresías, con la misma cuenta | Es lo que pidieron; también funciona si usa dos cuentas distintas | Rol global por persona |
| M3 | El alta es por email (invitación). En el primer ingreso, la invitación se convierte en membresía ligada al `sub` | El `sub` solo se conoce cuando la persona ingresa | Pedir el `sub` al admin (no lo conoce) |
| M4 | **Bloqueo optimista por pedido**: toda escritura en un pedido incluye su ítem `PEDIDO` con la condición `version = :v` | Las condiciones de DynamoDB no hacen sumas (`pagado + monto <= total`). El dominio calcula con datos leídos y la versión garantiza que nadie cambió el pedido entretanto. Corrige D5 y D6 | Condiciones aritméticas: no existen |
| M5 | Los **totales de caja se acumulan en el ítem `TURNO` dentro de la misma transacción del pago o retiro**. Los agregados `AGG#` del flujo de eventos son solo para reportes | El arqueo y el cierre son críticos y no pueden depender de un proceso asíncrono (riesgo R6) | Calcular el cierre desde `AGG#`: cifras atrasadas |
| M6 | Los trabajos de impresión de la comanda se crean **dentro de la transacción de enviar tanda** | "Enviado a cocina" significa que el trabajo ya existe. No depende de que el flujo de eventos esté al día | Crearlos en `procesador-eventos`: la cocina no imprime si el flujo se atrasa |
| M7 | El documento tributario se crea como `DTE#venta_id` en estado `pendiente` **dentro de la transacción de finalizar**, en la partición del turno | La caja lo ve de inmediato. La emisión sigue siendo asíncrona | Crearlo en `procesador-eventos` |
| M8 | `finalizar` exige turno abierto y recibe el tipo de documento y los datos del receptor | Hoy esos datos nunca llegan al backend (D8). Sin turno no hay a qué asociar la venta | — |
| M9 | El ítem `CMD#` guarda **también los rechazos de negocio** | El mismo `X-Command-Id` siempre devuelve la misma respuesta, y un código de autorización equivocado reintentado no suma dos intentos | Guardar solo los éxitos |
| M10 | Sin TTL en el historial de negocio (pedidos, pagos, turnos, documentos) | Cuesta centavos guardarlo. Borrarlo dejaría a S3 como única copia, y un evento perdido sería irrecuperable | TTL de 90 días |
| M11 | Índice secundario disperso `GSI1` en `operacion` solo para lo que `tareas-programadas` debe vigilar | Evita recorrer la tabla entera | `Scan` periódico |
| M12 | Para autorizar, **el autorizador elige su nombre y digita su código** | Un solo cálculo PBKDF2 por intento, bloqueo por autorizador y sin choques de códigos iguales (D13). Cambia la pantalla de retiro | Probar el código contra todos los admins |
| M13 | Un pedido en precuenta **no admite ítems nuevos** (409 `PEDIDO_EN_PRECUENTA`). Para agregarlos, el garzón **reabre la mesa con una confirmación explícita** (`POST .../reabrir` con `confirmado: true`): el pedido vuelve a `abierto` y la mesa a `ocupada`. Sin la confirmación responde 422 `CONFIRMACION_REQUERIDA` | Corrige D1 y cumple lo decidido el 2026-10-14. La reapertura queda en un evento (`pedido.reabierto`, con quién y si ya había pagos) | Reabrir automáticamente al agregar el ítem: el garzón no se enteraría de que invalida la precuenta impresa |
| M14 | Un pedido **sin ítems** puede cerrarse para liberar la mesa, sin documento tributario | Hoy se cierra igual (0 ≥ 0) y emitiría una boleta de $0 | Prohibirlo: la mesa quedaría tomada |
| M15 | Un `ValidationException` de DynamoDB (por ejemplo, un ítem de más de 400 KB) es un **defecto de código**: 500 y alerta, **no** contingencia | Reaplicarlo en la cola fallaría igual durante 90 minutos | Tratarlo como falla de infraestructura, que es lo que dice el texto de la regla |

---

## 1. Identificadores y convenciones

| Concepto | Qué es | Formato |
|---|---|---|
| **Cliente** (`tenant_id`) | La empresa que contrata la plataforma (por ejemplo "Restaurantes Pérez SpA"). Puede tener varias marcas y locales | `[a-z0-9_]{3,32}`, sin `#` |
| **Local** (`local_id`) | Un restaurante físico. Tiene su catálogo, salón, caja e impresoras. La marca es un atributo del local | ídem |
| **Persona** (`sub`) | Un empleado con cuenta de Google (dueño, admin, cajero, garzón, cocina). No es un comensal ni ustedes como operadores de la plataforma | el `sub` del ID token |
| IDs generados | Pedidos, ítems, pagos, mesas, productos, eventos… | ULID (26 caracteres, ordenable por tiempo), generado en `pos_dominio` |
| `X-Command-Id` | Lo genera el cliente por cada acción del usuario | ULID; se valida el formato |

Convenciones de los ítems:

- `L` abrevia `TENANT#<tenant_id>#LOCAL#<local_id>`. Toda clave de partición empieza con el cliente,
  salvo las tres excepciones de §4.3.
- Todo ítem lleva `tipo_item` (por ejemplo `PEDIDO`, `ITEM`, `CMD`) para filtrar y depurar.
- `version` (número) en todo ítem que se modifica; cada escritura la sube en 1.
- Montos: enteros en pesos. Porcentajes de umbral: **puntos base** enteros (2 % = 200). Cantidades de
  inventario: **milésimas** enteras (1,5 kg = 1500), igual de exacto que el `NUMERIC(12,3)` actual.
- Fechas: texto ISO-8601 en UTC con milisegundos (`2026-10-13T22:15:03.120Z`).
  `fecha_operativa` = fecha en hora de Chile de la apertura del turno.
- TTL: atributo `expira_en`, número en segundos epoch. **DynamoDB puede tardar hasta 48 h en borrar un
  ítem vencido**, así que el código siempre compara `expira_en` con la hora actual; nunca asume que un
  ítem vencido ya no existe.
- Toda expresión usa `ExpressionAttributeNames` (`#estado`, `#total`, `#version`…).

---

## 2. Tablas

| | `configuracion` | `operacion` |
|---|---|---|
| Claves | `PK` (S), `SK` (S) | `PK` (S), `SK` (S) |
| Capacidad | bajo demanda | bajo demanda |
| TTL | no | sí, atributo `expira_en` |
| Streams | no | sí, tipo de vista **`NEW_IMAGE`** |
| Índice | `GSI1` (`GSI1PK`, `GSI1SK`), proyección `INCLUDE`: `nombre`, `email`, `rol`, `estado`, `sub`, `tipo_item` | `GSI1` (`GSI1PK`, `GSI1SK`), proyección `ALL`, **disperso** |
| Uso del índice | Listar el personal de un local sin exponer hashes de código | Lo que vigila `tareas-programadas` |

Filtro del disparador `operacion` → `procesador-eventos`:

```json
{ "eventName": ["INSERT"], "dynamodb": { "Keys": { "SK": { "S": [ { "prefix": "EVT#" } ] } } } }
```

`INSERT` excluye los borrados por TTL (`REMOVE`). Además, el código descarta cualquier registro cuyo
`tipo_item` no sea `EVT`.

---

## 3. Patrones de acceso

`C` = lectura consistente. `E` = eventual. Las lecturas de identidad, configuración e impresora se
guardan en memoria de la función hasta 60 s.

### 3.1 Pantallas

| # | Pantalla o acción | Lecturas | Tabla y clave | Tipo |
|---|---|---|---|---|
| A1 | Ingreso (`GET /yo`) | perfil + membresías | cfg `PK=USER#<sub>` | Query E |
| A2 | Primer ingreso | invitaciones del email | cfg `PK=INVITACION#<email>` | Query C |
| A3 | Plano del salón: estructura | mesas y sectores | cfg `PK=L`, `SK begins_with MESA#` y `SECTOR#` | Query E (se guarda en la PWA) |
| A4 | Plano del salón: estado (refresco periódico) | estado de cada mesa | op `PK=L#SALON` | Query E |
| A5 | Carta en la comanda | versión del catálogo; productos si cambió | cfg `L / CATALOGO`; `PK=L, SK begins_with PROD#` | Get E; Query E |
| A6 | Comanda de una mesa | pedido + ítems + pagos | op `PK=L#PED#<pedido_id>` | Query C |
| A7 | Caja: mesas por cobrar | mesas en precuenta → sus pedidos | A4 + A6 por cada una | Query |
| A8 | Caja: turno actual | puntero + turno + retiros + documentos | op `L#CAJA / TURNO_ABIERTO`; `PK=L#TURNO#<turno_id>` | Get C; Query C |
| A9 | Caja: documentos del turno | estado de cada documento | op `PK=L#TURNO#<turno_id>`, `SK begins_with DTE#` | Query C |
| A10 | Caja: bandeja de conflictos | conflictos abiertos | op `PK=L#CONFLICTO` | Query C |
| A11 | Caja: impresiones retenidas | trabajos retenidos | op `PK=L#IMPRET` | Query C |
| A12 | Retiro: lista de autorizadores | dueños y admins del local con código | cfg `GSI1PK=L#PERSONAL` (filtro por rol) | Query E |
| A13 | Admin: personal | membresías e invitaciones del local | cfg `GSI1PK=L#PERSONAL` | Query E |
| A14 | Admin: catálogo, cuartos, impresoras, inventario, recetas, configuración | por prefijo | cfg `PK=L`, `SK begins_with PROD#`, `CUARTO#`, `IMPRESORA#`, `MP#`, `RECETA#`; `L / LOCAL` | Query E |
| A15 | Reporte de un turno | turno + agregados + documentos + retiros | op `PK=L#TURNO#<turno_id>` | Query C |
| A16 | Lista de turnos por fecha | índice de turnos | op `PK=L#CAJA`, `SK between TURNO#<ulid_desde> and TURNO#<ulid_hasta>` | Query E |
| A17 | Resumen del día | agregado diario | op `L#DIA#<fecha> / AGG#RESUMEN` | Get E |

### 3.2 Funciones sin pantalla

| # | Función | Lecturas | Clave | Tipo |
|---|---|---|---|---|
| F1 | Toda función de la API | membresía del usuario | cfg `PK=USER#<sub>` | Query E, en memoria 60 s |
| F2 | `GET /salud` | ítem centinela | op y cfg `SALUD / SALUD` | Get E |
| F3 | `impresion`: autenticar | impresora | cfg `L / IMPRESORA#<id>` | Get E, en memoria 60 s |
| F4 | `impresion`: siguiente trabajo | el más antiguo pendiente | op `PK=L#IMP#<id>`, `SK begins_with PEND#`, `Limit 1` | Query C |
| F5 | `emision-dte` | estado del documento | op `L#TURNO#<turno_id> / DTE#<venta_id>` | Get C |
| F6 | `emision-dte` | impresora de la caja | cfg `L / LOCAL` (`impresora_caja_id`) | Get E |
| F7 | `procesador-eventos` | ¿efecto ya aplicado? | se resuelve con condición al escribir, sin leer | — |
| F8 | `drenador-contingencia` | igual que `pedidos` | ídem A6, F1 | — |
| F9 | `tareas-programadas` | lo vigilado | op `GSI1PK=VIGILAR#<tipo>`, `GSI1SK < <límite>` | Query E |

---

## 4. Diseño de claves

### 4.1 Tabla `configuracion`

| PK | SK | Contenido principal | Notas |
|---|---|---|---|
| `TENANT#<t>` | `TENANT` | nombre, estado | Lo crean ustedes (operadores) en la consola |
| `L` | `LOCAL` | nombre_local, marca, propina_sugerida_pct, umbral_diferencia_pb, umbral_diferencia_minimo, impresora_caja_id, version | Reemplaza `configuracion_restaurante` |
| `L` | `ESTACION#<id>` | nombre, tipo=`caja` | Equipos registrados como PC de caja (habilita la cola local) |
| `L` | `SECTOR#<id>` | nombre, activo, version | |
| `L` | `MESA#<id>` | sector_id, sector_nombre, numero, capacidad, activa, version | Solo **estructura**; el estado vive en `operacion` |
| `L` | `UNICO#<tipo>#<valor>` | ref_id | Garantiza unicidad: `MESA#<sector>#<numero>`, `SECTOR#<nombre>`, `CUARTO#<nombre>`, `EMAIL#<email>`. Corrige D15 |
| `L` | `CATALOGO` | version | Sube en cada cambio de catálogo; la PWA solo recarga si cambió |
| `L` | `PROD#<id>` | nombre, categoria, precio, cuarto_id, activo, descripcion, `modificadores: [{modificador_id, nombre, precio_adicional}]`, version | Modificadores embebidos con **ID estable** (corrige D14) |
| `L` | `CUARTO#<id>` | nombre, descripcion, activo, impresora_id, version | |
| `L` | `IMPRESORA#<id>` | nombre, modelo, protocolo, activa, clave_hash, clave_sal, clave_iter, version | La clave en claro se muestra una sola vez al crearla o rotarla |
| `L` | `MP#<id>` | nombre, unidad, stock_actual_mil, stock_minimo_mil, activo, version | Cantidades en milésimas |
| `L` | `RECETA#<producto_id>` | `ingredientes: [{materia_prima_id, cantidad_mil}]`, version | Una por producto |
| `USER#<sub>` | `PERFIL` | email, nombre, estado (`activo`/`archivado`), version | |
| `USER#<sub>` | `MEMBRESIA#<t>#<l>` | tenant_id, local_id, rol, estado, nombre, email, pin_hash, pin_sal, pin_iter, version; `GSI1PK=L#PERSONAL`, `GSI1SK=<nombre>#<sub>` | **Fuente única del rol**. El código de autorización es por membresía |
| `INVITACION#<email>` | `MEMBRESIA#<t>#<l>` | rol, nombre, invitado_por; `GSI1PK=L#PERSONAL`, `GSI1SK=<nombre>#INV#<email>` | Se borra al vincularse |
| `SALUD` | `SALUD` | — | Centinela para `/salud` |

### 4.2 Tabla `operacion`

| PK | SK | Contenido principal | TTL | GSI1 |
|---|---|---|---|---|
| `L#SALON` | `MESA#<mesa_id>` | estado (`libre`/`ocupada`/`precuenta`/`bloqueada`), pedido_id, garzon_id, version | — | — |
| `L#PED#<pedido_id>` | `PEDIDO` | mesa_id, garzon_id, estado (`abierto`/`precuenta`/`cerrado`), total, pagado, propina_total, n_items, n_tandas, documento `{tipo, receptor}`, turno_cierre_id, origen, creado_en, cerrado_en, version | — | — |
| `L#PED#<pedido_id>` | `ITEM#<item_id>` | producto_id, nombre, categoria, cuarto_id, modificador_id, modificador_nombre, cantidad, cobrado, precio_unitario, estado (`en_espera`/`enviado`), tanda, observacion, creado_en, enviado_en | — | — |
| `L#PED#<pedido_id>` | `PAGO#<pago_id>` | turno_id, metodo, monto, propina, codigo_autorizacion_pos, efectivo_recibido, vuelto, tipo_division, items_cobrados, usuario_id, fecha | — | — |
| `L#CAJA` | `TURNO_ABIERTO` | turno_id, abierto_en | — | `VIGILAR#TURNO` / `abierto_en` |
| `L#CAJA` | `TURNO#<turno_id>` | fecha_operativa, estado, resumen al cerrar | — | — |
| `L#TURNO#<turno_id>` | `TURNO` | estado, monto_apertura, usuario_apertura_id, abierto_en, primer_conteo, segundo_conteo, requiere_segundo_conteo, conciliacion, **tot_efectivo, tot_debito, tot_credito, tot_transferencia** (monto + propina), tot_retiros, n_pagos, n_ventas, tot_ventas, resultado, usuario_cierre_id, cerrado_en, version | — | — |
| `L#TURNO#<turno_id>` | `RETIRO#<retiro_id>` | monto, motivo, usuario_id, autorizado_por, creado_en | — | — |
| `L#TURNO#<turno_id>` | `DTE#<venta_id>` | estado, tipo, receptor, total, folio, timbre, motivo_rechazo, intentos, version | — | `VIGILAR#DTE` mientras esté `pendiente` o `enviando` |
| `L#TURNO#<turno_id>` | `AGG#RESUMEN`, `AGG#GARZON#<sub>` | contadores para reportes (los escribe `procesador-eventos`) | — | — |
| `L#DIA#<fecha>` | `AGG#RESUMEN` | contadores del día | — | — |
| `L#IMP#<impresora_id>` | `PEND#<trabajo_id>` | tipo (`comanda`/`boleta`/`factura`), contenido, pedido_id, tanda, origen, creado_en, entregado_en | — | `VIGILAR#IMPRESION` / `creado_en` |
| `L#IMP#<impresora_id>` | `HECHO#<trabajo_id>` | igual + impreso_en | 7 días | — |
| `L#IMPRET` | `RET#<trabajo_id>` | impresora_id + datos del trabajo, estado `retenido_contingencia` | — | — |
| `L#CONFLICTO` | `CONFLICTO#<ulid>` | comando completo, motivo, estado (`abierto`/`resuelto`/`descartado`), resuelto_por | — | — |
| `L#AUT` | `BLOQUEO#<sub_autorizador>` | intentos, ventana_hasta | 15 min | — |
| `L#CMD#<command_id>` | `CMD` | tipo, estado (`aplicado`/`rechazado`), http_status, respuesta, hash_cuerpo, usuario_id, origen, creado_en | 48 h | — |
| `L#EVT` | `EVT#<event_id>` | tipo, v, tenant_id, local_id, ocurrido_en, usuario_id, command_id, origen, datos | 7 días | — |
| `L#PROC` | `<efecto>#<event_id>` | marca de evento procesado | 8 días | — |
| `TENANT#<t>` | `CONTADOR#FOLIO#<tipo>` | ultimo | — | — |
| `SALUD` | `SALUD` | — | — | — |

### 4.3 Excepciones a "la partición empieza con el cliente"

| Clave | Por qué |
|---|---|
| `USER#<sub>` | Lo exige la decisión cerrada: al llegar la petición no se sabe el cliente; este ítem lo dice. Solo contiene membresías |
| `INVITACION#<email>` | Antes del primer ingreso solo se conoce el email |
| `SALUD` | Centinela técnico sin datos |
| `GSI1PK=VIGILAR#<tipo>` en `operacion` | Es un índice de vigilancia global, no una partición de la tabla |

### 4.4 Prefijos reservados (fuera de alcance por ahora)

`L#RESERVA#…`, `L / REGLA_RESERVA#…`, `L#EXTERNO#…`, `L#PED#… / DESCUENTO#…`, `… / ANULACION#…`.

---

## 5. Ítems especiales

**Comando (`CMD`)**. Es la base de la idempotencia. Va primero en toda transacción de escritura con
`attribute_not_exists(PK)`.
- Si la transacción se cancela **solo** por esa condición, es un duplicado: se lee el `CMD` y se
  devuelve la respuesta guardada, con el mismo código HTTP.
- Si el `CMD` existe pero `hash_cuerpo` no coincide con el cuerpo nuevo, se responde **422
  `COMANDO_REUTILIZADO`**: el cliente reutilizó el ID para otra cosa.
- Los rechazos de negocio también se guardan (M9), con un `PutItem` aparte.
- Antes de ejecutar, un `GetItem` del `CMD` evita repetir trabajo en los reintentos comunes.

**Evento (`EVT`)**. Va al final de toda transacción de negocio. Su `datos` lleva lo necesario para
los efectos sin volver a leer, por ejemplo la venta completa en `venta.cerrada`. Tipos:
`pedido.abierto`, `item.agregado`, `item.modificado`, `item.quitado`, `tanda.enviada`,
`precuenta.emitida`, `pago.registrado`, `venta.cerrada`, `pedido.cerrado_sin_venta`, `turno.abierto`,
`conteo.registrado`, `conciliacion.registrada`, `turno.cerrado`, `retiro.registrado`,
`autorizacion.concedida`, `autorizacion.rechazada`, `impresion.liberada`, `impresion.descartada`,
`conflicto.registrado`, `conflicto.resuelto`, `dte.emitido`, `dte.rechazado`, `dte.fallido` y los de
configuración (`catalogo.actualizado`, `personal.*`, `mesa.*`, `local.actualizado`).

**Marca de procesado (`PROC`)**. `procesador-eventos` escribe cada efecto en DynamoDB junto con
`L#PROC / <efecto>#<event_id>` y la condición `attribute_not_exists(PK)`. Si la condición falla, ese
efecto ya se aplicó y se omite. Los efectos en S3 usan claves deterministas por `event_id` o
`venta_id`, así que sobrescribir es inocuo. El aviso por SNS escribe la marca **después** de publicar
con éxito: puede llegar un correo duplicado, pero nunca se pierde uno.

**Agregados**. `AGG#RESUMEN` y `AGG#GARZON#<sub>` del turno, y `AGG#RESUMEN` del día. Se alimentan de
`venta.cerrada` y `retiro.registrado` con `ADD`. Atribución: la venta cuenta en el turno donde se
**cerró**; el efectivo cuenta en el turno donde se **cobró** (eso es `TURNO.tot_*`, M5).

**Folios**. `TENANT#<t> / CONTADOR#FOLIO#<boleta|factura>` con `UpdateItem ADD ultimo :1` y
`ReturnValues=UPDATED_NEW`. Una transacción no puede devolver valores, así que la asignación va en
dos pasos:
1. Si el `DTE` ya tiene folio, se reutiliza.
2. Si no, se incrementa el contador y se escribe el folio en el `DTE` con `attribute_not_exists(folio)`.

Una caída entre los dos pasos deja un **hueco** de numeración. Con el proveedor simulado es
aceptable; con uno real, los folios vendrán del CAF del proveedor.

**Documento (`DTE#<venta_id>`)**. `venta_id = pedido_id`. Estados: `pendiente → enviando → emitido`
(con folio y timbre), `rechazado` (con motivo) o `fallido`. `emision-dte` marca `fallido` cuando el
mensaje está en su última recepción (`ApproximateReceiveCount` = máximo de recepciones) y vuelve a
fallar; entonces SQS lo mueve a la cola de fallidos.

**Conflicto (`CONFLICTO#`)**. Lo escribe `drenador-contingencia` cuando el dominio rechaza un comando
reaplicado. Guarda el comando completo para que la caja decida.

**Bloqueo de autorización (`BLOQUEO#`)**. Cuenta los intentos fallidos por autorizador en una ventana
de 15 minutos. Con 5 intentos dentro de la ventana, se rechaza sin calcular el hash.

---

## 6. Operaciones críticas: qué escribe cada transacción

Notación: `cfg:` = tabla `configuracion`; sin prefijo = `operacion`. `v` = versión leída. Toda
transacción de negocio empieza con `Put CMD` (`attribute_not_exists(PK)`) y termina con `Put EVT`;
se omiten de las tablas para no repetirlos, pero **cuentan para el límite de 100**.

### 6.1 Salón y comanda (`pedidos`)

| Operación | Escrituras además de CMD y EVT | Condiciones | Ítems |
|---|---|---|---|
| **Abrir pedido** (o devolver el existente) | Put `L#PED#p / PEDIDO`; Update `L#SALON / MESA#m` (`estado=ocupada`, `pedido_id=p`, `garzon_id=if_not_exists`) | PEDIDO: `attribute_not_exists(PK)`. MESA: `attribute_not_exists(pedido_id) AND (attribute_not_exists(estado) OR estado = libre)`. Si falla la de la mesa, se relee: con pedido → se devuelve ese (200); bloqueada → 409 `MESA_BLOQUEADA` | 4 |
| **Agregar ítem** | Put `ITEM#i`; Update `PEDIDO` (total, n_items, version) | PEDIDO: `version = v AND estado = abierto` (corrige D1) | 4 |
| **Modificar ítem** (cantidad u observación) | Update `ITEM#i`; Update `PEDIDO` | ITEM: `estado = en_espera` (corrige D3). PEDIDO: `version = v AND estado = abierto` | 4 |
| **Quitar ítem en espera** | Delete `ITEM#i`; Update `PEDIDO` | ITEM: `estado = en_espera`. PEDIDO: versión y abierto | 4 |
| **Enviar tanda** | Update `PEDIDO` (n_tandas); Update `ITEM#…` × k (`enviado`, tanda, enviado_en); Put `L#IMP#<imp> / PEND#…` × j, uno por impresora (o `L#IMPRET / RET#…` si el origen es contingencia) | PEDIDO: versión y abierto. Cada ITEM: `estado = en_espera`. Cada trabajo: `attribute_not_exists(PK)`. Si el cuarto no tiene impresora activa, no se crea trabajo y la respuesta y el evento lo indican (`sin_impresora`). Sin ítems en espera: 200 sin escribir, como hoy | 3 + k + j |
| **Precuenta** | Update `PEDIDO` (`precuenta`); Update `L#SALON / MESA#m` (`precuenta`) | PEDIDO: versión, `estado = abierto`, `n_items > 0` (corrige D2). MESA: `pedido_id = p` | 4 |
| **Reabrir pedido** (precuenta → abierto) | Update `PEDIDO` (`abierto`); Update `L#SALON / MESA#m` (`ocupada`) | PEDIDO: `version = v AND estado = precuenta`. MESA: `pedido_id = p`. Si ya está `abierto`: 200 sin escribir. Si está `cerrado`: 409 `PEDIDO_CERRADO`. Con pagos parciales se permite; el saldo se recalcula | 4 |
| **Bloquear o desbloquear mesa** | Update `L#SALON / MESA#m` | bloquear: `attribute_not_exists(pedido_id)`; desbloquear: `estado = bloqueada` (corrige D4) | 3 |

### 6.2 Caja (`caja`)

| Operación | Escrituras además de CMD y EVT | Condiciones | Ítems |
|---|---|---|---|
| **Registrar pago** (1 a N medios, un solo comando) | Put `PAGO#…` × N; Update `PEDIDO` (pagado, propina_total); Update `ITEM#…` × k (cobrado), solo si es división por ítems; Update `L#TURNO#tu / TURNO` (`ADD tot_<medio>`, n_pagos) | PEDIDO: versión y `estado IN (abierto, precuenta)`. El dominio valida monto ≤ saldo e ítems ≤ disponibles (corrige D6, D7, D9). TURNO: `estado = abierto` | 4 + N + k |
| **Finalizar venta** | Update `PEDIDO` (`cerrado`, documento, turno_cierre_id); Update `L#SALON / MESA#m` (`libre`, quitar pedido y garzón); Put `L#TURNO#tu / DTE#p` (`pendiente`, GSI1); Update `TURNO` (n_ventas, tot_ventas) | PEDIDO: versión, `estado IN (abierto, precuenta)`; el dominio exige pagado = total. MESA: `pedido_id = p`. DTE: `attribute_not_exists(PK)`. TURNO: abierto. Pedido vacío: sin DTE y evento `pedido.cerrado_sin_venta` (M14) | 6 |
| **Abrir turno** | Put `L#CAJA / TURNO_ABIERTO` (GSI1); Put `L#TURNO#tu / TURNO`; Put `L#CAJA / TURNO#tu` | `TURNO_ABIERTO`: `attribute_not_exists(PK)`. Así hay un solo turno abierto por local | 5 |
| **Conteo de efectivo** | Update `TURNO` | `version = v AND estado = abierto`, más `attribute_not_exists(primer_conteo)` o `requiere_segundo_conteo = true AND attribute_not_exists(segundo_conteo)`. El esperado sale de `TURNO.tot_*`, leído en la misma versión | 3 |
| **Conciliación del terminal** | Update `TURNO` | versión y abierto | 3 |
| **Cerrar turno** | Update `TURNO` (cerrado, resultado); Delete `L#CAJA / TURNO_ABIERTO`; Update `L#CAJA / TURNO#tu` | TURNO: versión, abierto y conteos completos. TURNO_ABIERTO: `turno_id = tu` | 5 |
| **Retiro autorizado** | Put `RETIRO#r`; Update `TURNO` (`ADD tot_retiros`); Delete `L#AUT / BLOQUEO#aut`; Put EVT `autorizacion.concedida` | TURNO: abierto. Antes de escribir se verifica el bloqueo y el código (PBKDF2 + `hmac.compare_digest`) | 6 |
| **Retiro con código inválido** | Put CMD (`rechazado`, 403); Update `L#AUT / BLOQUEO#aut` (`intentos + 1`, o reinicio si la ventana venció); Put EVT `autorizacion.rechazada` | BLOQUEO: `version = v` o `attribute_not_exists(PK)` | 3 |
| **Liberar o descartar impresión retenida** | Delete `L#IMPRET / RET#j`; si se libera, Put `L#IMP#i / PEND#j` | RET: `attribute_exists(PK)` | 3–4 |
| **Resolver conflicto** | Update `L#CONFLICTO / CONFLICTO#c` | `estado = abierto` | 3 |

### 6.3 Administración (`administracion`, transacciones entre las dos tablas)

| Operación | Escrituras | Condiciones |
|---|---|---|
| Crear o editar mesa | cfg: Put/Update `MESA#m`; Put `UNICO#MESA#<sector>#<num>` (y Delete del anterior si cambia); op: CMD, EVT | UNICO: `attribute_not_exists(PK)` → 409 si se repite. MESA: versión |
| Crear o editar sector o cuarto | ídem con `UNICO#SECTOR#…` / `UNICO#CUARTO#…` | ídem |
| Crear o editar producto | cfg: Put/Update `PROD#p`; Update `CATALOGO` (`ADD version`); op: CMD, EVT | PROD: versión |
| Invitar persona | cfg: Put `INVITACION#email / MEMBRESIA#t#l`; Put `L / UNICO#EMAIL#email`; op: CMD, EVT | ambos `attribute_not_exists`. Solo un dueño invita dueños o admins (corrige D16) |
| Primer ingreso (vincular) | cfg: Put `USER#sub / PERFIL`; por cada invitación: Put `MEMBRESIA#t#l` + Delete la invitación; Update `UNICO#EMAIL` (sub) | PERFIL: `attribute_not_exists`; invitación: `attribute_exists`. Es idempotente: reintentar no duplica |
| Cambiar rol o archivar | cfg: Update `USER#sub / MEMBRESIA#t#l`; op: CMD, EVT | versión. Nadie cambia su propio rol; solo un dueño toca membresías de dueño |
| Definir mi código | cfg: Update `MEMBRESIA` (pin_hash, pin_sal, pin_iter) | solo rol dueño o admin |
| Crear o rotar impresora | cfg: Put/Update `IMPRESORA#i` (clave_hash); op: CMD, EVT | versión |

Nunca se borra una persona: se **archiva** (estado `archivado`). Así se evita la consulta de
historial de `tiene_historial` y se conserva la auditoría (responde P15 para el personal).

### 6.4 Asíncronas

| Función | Escrituras | Condiciones |
|---|---|---|
| `procesador-eventos`: agregados | Update `AGG#RESUMEN` (turno), `AGG#GARZON#sub`, `L#DIA#f / AGG#RESUMEN` con `ADD`; Put `L#PROC / AGG#<event_id>` | PROC: `attribute_not_exists(PK)` |
| `emision-dte`: tomar | Update `DTE` → `enviando` (`intentos + 1`) | `estado IN (pendiente, enviando)` |
| `emision-dte`: emitido | Update `DTE` (`emitido`, folio, timbre, quitar GSI1); Put `L#IMP#<caja> / PEND#DTE-<venta_id>`; Put EVT `dte.emitido` | DTE: `estado = enviando`. Trabajo: `attribute_not_exists` (clave determinista, no duplica la boleta) |
| `emision-dte`: rechazado | Update `DTE` (`rechazado`, motivo); Put EVT `dte.rechazado` | `estado = enviando` |
| `drenador-contingencia` | las mismas transacciones de §6.1, con `origen = contingencia` | Si el dominio rechaza: Put CMD (`rechazado`) + Put `CONFLICTO#` + Put EVT `conflicto.registrado` (3 ítems) |
| `impresion`: confirmar | Delete `PEND#j`; Put `HECHO#j` | PEND: `attribute_exists(PK)`; un segundo aviso de impresión es 200 sin efecto |

---

## 7. Límites de transacción

| Operación | Fórmula | Tope que valida el dominio |
|---|---|---|
| Enviar tanda | 3 + k ítems + j impresoras | k ≤ 80, j ≤ 10 → máx. 93 |
| Registrar pago | 4 + N medios + k ítems cobrados | N ≤ 6, k ≤ 80 → máx. 90 |
| Las demás | ≤ 8 | — |

Tamaño: el ítem más grande es el `EVT` de `venta.cerrada` (≈ 200 bytes por línea). Con 80 líneas son
≈ 20 KB, lejos de los 400 KB por ítem y los 4 MB por transacción. El dominio rechaza una observación
de más de 500 caracteres y un pedido de más de 300 líneas, para acotar el tamaño de la partición y
del evento.

---

## 8. Cómo se interpreta una transacción cancelada

`TransactionCanceledException` trae `CancellationReasons`, una por ítem y en el mismo orden.

| Motivo | En qué ítem | Interpretación | Respuesta |
|---|---|---|---|
| `ConditionalCheckFailed` | **solo** el `CMD` | Comando duplicado | Respuesta guardada |
| `ConditionalCheckFailed` | `PEDIDO`/`TURNO` por `version` | Alguien escribió entremedio | Se relee y se reintenta **una vez**; si vuelve a fallar → 409 `CONFLICTO_CONCURRENCIA` |
| `ConditionalCheckFailed` | cualquier otro | Rechazo de negocio (estado no válido) | 409 o 422 con código específico |
| `TransactionConflict` | — | Otra transacción tocaba el mismo ítem | 2 reintentos con espera aleatoria; si persiste → infraestructura |
| `ThrottlingError`, `ProvisionedThroughputExceeded`, `RequestLimitExceeded`, `InternalServerError`, tiempo agotado, error de red | — | Infraestructura | `pedidos` encola en contingencia (202); las demás responden 503 |
| `ValidationError` | — | Defecto de código (M15) | 500 y alerta |

---

## 9. Costo estimado

Escrituras en transacción = 2 unidades por KB y por ítem. Una venta típica (abrir mesa, 5 ítems en 2
tandas, precuenta, un pago, cerrar, documento, 3 impresiones, efectos asíncronos) ≈ **150 unidades de
escritura**. A USD 0,625 por millón en bajo demanda (`us-east-1`), son ≈ USD 0,0001 por venta: con
9.000 ventas al mes, **menos de USD 1 al mes**. Las lecturas del refresco del salón (Query de ≈ 2 KB
cada 10 s por equipo) son el segundo costo y siguen en centavos. Lambda leyendo Streams no cobra
lecturas.

---

## 10. Riesgos de este modelo y su mitigación

| # | Riesgo | Mitigación |
|---|---|---|
| R6 | Cierre con cifras atrasadas | M5: totales síncronos en `TURNO` |
| R8 | Ítems vencidos por TTL que siguen existiendo hasta 48 h | El código compara `expira_en` siempre (bloqueos, CMD) |
| R9 | Contención en un pedido muy activo (dos garzones y la caja) | Reintento único con relectura; el 409 llega a la PWA con un mensaje claro |
| R10 | Huecos de folio | Documentado; solo con proveedor simulado |
| R11 | Duplicar la boleta impresa | Trabajo con clave determinista `PEND#DTE-<venta_id>` y condición |
| R12 | Membresía cambiada que sigue en la memoria de una función | Máximo 60 s, como pide la regla |
| R13 | El `local_id` viene en la ruta | Solo selecciona la membresía; sin membresía activa en ese local → 403. El rol y el cliente salen siempre de `configuracion` |
| R14 | `contingencia` no lee DynamoDB, así que no puede autorizar | Encola con el `sub` del token; `drenador-contingencia` autoriza al reaplicar. Sin permiso → conflicto, no escritura |
| R3 | Zona horaria de Chile en Lambda | `fecha_operativa` se calcula en `pos_dominio` con `zoneinfo`. Si el runtime no trae la base de zonas, la capa incluye el archivo de `America/Santiago` (dato, no dependencia) y se carga con `ZoneInfo.from_file`. `/salud` informa cuál se usó |
