# 08 — Mensajería asíncrona: canales, destinos, reglas y mensajes fallidos

Qué hace el sistema en segundo plano, quién recibe cada mensaje, qué pasa cuando algo falla y cómo se
administra todo desde la PWA. Al final, la relación con cada criterio de la pauta de evaluación.

## 1. Catálogo central de canales y rutas

Un solo archivo declara toda la mensajería: `lambdas/capa/python/pos_dominio/mensajeria.py`.

| Contiene | Para qué |
|---|---|
| `CANALES` | Cada canal: flujo de eventos, colas, colas de fallidos, temas y regla programada. Para cada uno: quién envía, quién procesa, si es FIFO, visibilidad, recepciones antes de apartar y su cola de fallidos |
| `RUTAS` | Qué evento de negocio llega a qué canal y a qué consumidor, con su condición |
| `AVISOS` | Los avisos que se publican, a qué tema van y si un destino administrable puede recibirlos |
| Validación | Reglas para crear destinos y reglas (nombres, tipos, correos y avisos permitidos) |

Quién lo usa, y así nadie repite la configuración:
- **`desplegar.sh`** crea las colas leyendo el catálogo (`ayudante.py canales`): nombres, visibilidad,
  FIFO, cola de fallidos y recepciones. Las alarmas usan los mismos nombres.
- **`procesador-eventos` y `tareas-programadas`** publican cada aviso en el tema que dice el catálogo,
  con sus atributos (`aviso`, `tenant_id`, `local_id`, `prueba`).
- **La función `mensajeria`** valida las solicitudes y arma las reglas con el catálogo, y lo muestra en
  la pestaña «Canales y rutas».
- **Las pruebas** (`tests/dominio/test_mensajeria_catalogo.py`) fallan si la tabla de colas de
  `02-api-gateway.md` o `desplegar.sh` se desvían del catálogo, si el código publica un aviso que no
  está en él o si una ruta apunta a un canal inexistente.

Cambiar una cola o un aviso es cambiar una línea del catálogo; las pruebas avisan si algo quedó
inconsistente.

## 2. Canales y rutas por caso de uso

| Caso de uso | Canal | Consumidor | Qué hace |
|---|---|---|---|
| Cualquier cambio de negocio (venta, pago, comanda, turno…) | Flujo de eventos de `operacion` (DynamoDB Streams, patrón outbox) | `procesador-eventos` | Archivo histórico, totales de reportes, comprobante y distribución de avisos |
| Venta cerrada → documento tributario | Cola `dte-emision` | `emision-dte` | Emite la boleta o factura y la manda a imprimir |
| Documento sin intentos por 15 min | Regla programada → cola `dte-emision` | `tareas-programadas` → `emision-dte` | Reencola documentos atascados |
| Comanda durante una falla | Cola FIFO `contingencia-comandas.fifo` (orden por mesa) | `drenador-contingencia` | Reaplica en orden; si ya no se puede, registra un conflicto |
| Aviso del negocio (cierre con diferencia, documento rechazado, comanda en conflicto, código bloqueado, turno abierto demasiado) | Tema `pos-avisos-dueno` | Destinos administrables, según sus reglas | Correo o cola |
| Alerta técnica (documento fallido, impresora sin retirar, alarmas) | Tema `pos-alertas-tecnicas` | Equipo técnico | Correo |

## 3. Destinos y reglas de distribución

- Un **destino** es quien recibe avisos. Hay dos tipos:
  - **correo**: una suscripción de email, que AWS pide confirmar una vez;
  - **cola**: una cola SQS propia (`pos-destino-<id>`) para que otro sistema la consuma, por ejemplo
    contabilidad. Desde la PWA se puede ver lo que llegó.
- Una **regla de distribución** dice qué avisos recibe un destino. Se implementa como la política de
  filtro de su suscripción: `{"aviso": [...], "tenant_id": [<cliente>], "local_id": [<local>]}`. Así un
  destino recibe **solo los avisos elegidos y solo de su local**; SNS descarta el resto.
- Ejemplo: «Jefe de turno» (correo) con las reglas *comanda en conflicto* y *código bloqueado*;
  «Contabilidad» (cola) con *documento rechazado* y *cierre con diferencia*. Un documento rechazado
  llega solo a Contabilidad.
- **Mensaje de prueba**: publica un aviso marcado como prueba con los mismos atributos de uno real.
  La respuesta dice qué destinos deben recibirlo y por qué. Lo demuestran `probar_nube.py` §3 y
  `validar_despliegue.py` (paso 13): el aviso llega a la cola del destino con la regla y no a la del
  otro.

## 4. Separación entre negocio y mensajería

- **Las operaciones de negocio** (`pos_dominio/operaciones/*`) solo declaran «ocurrió este evento». El
  evento se guarda en la **misma transacción** que el cambio (outbox), así que nunca hay un cambio sin
  evento ni un evento sin cambio. No conocen colas ni temas.
- **`efectos.py`** decide en funciones puras qué produce cada evento: totales, archivo, comprobante y
  avisos.
- **El catálogo** decide a dónde va cada cosa.
- **`infra/aws.py` e `infra/mensajeria_aws.py`** son los únicos que hablan con SQS y SNS.

Efecto: las reglas del negocio se prueban sin AWS. Cambiar un destino o una cola no toca el negocio, y
cambiar el negocio no toca la mensajería.

## 5. Consumidores

| Consumidor | Se activa con | Responsabilidad |
|---|---|---|
| `procesador-eventos` | Cada evento nuevo (Streams, filtro solo `EVT#`) | Efectos de los eventos y publicación de avisos |
| `emision-dte` | Mensajes en `dte-emision` (lotes de 5, concurrencia 2) | Emitir documentos tributarios |
| `drenador-contingencia` | Mensajes en `contingencia-comandas.fifo` | Reaplicar comandas en orden por mesa |
| `tareas-programadas` | Regla EventBridge cada 5 minutos | Reencolar documentos y vigilar turnos e impresoras |

Los productores son las funciones de la API (al escribir eventos y comandas de contingencia),
`procesador-eventos` (publica en `dte-emision` y en los temas) y `tareas-programadas`.

## 6. Confirmación, reintentos y mensajes fallidos

| Consumidor | Éxito | Error recuperable | Error definitivo |
|---|---|---|---|
| `procesador-eventos` | Confirma registro por registro; cada efecto queda marcado y no se repite (`PROC#`) | Devuelve el registro que falló; se reintenta desde ahí hasta 10 veces dividiendo el lote | Pasados los reintentos o 1 hora, el lote va a `procesador-eventos-fallidos` |
| `emision-dte` | Borra el mensaje; el documento queda `emitido` | Proveedor caído: el mensaje vuelve con espera creciente; hasta 5 recepciones | Rechazo del proveedor: `rechazado`, sin reintento, aviso al dueño. Tras 5 intentos fallidos: `fallido`, el mensaje va a `dte-emision-fallidos` y llega una alerta técnica |
| `drenador-contingencia` | Aplica el comando (idempotente por `X-Command-Id`) | DynamoDB caído: reintento (unos 90 min, 15 recepciones) sin romper el orden de la mesa | Rechazo de negocio: se registra un **conflicto** y se avisa al dueño. Tras 15 intentos, el mensaje va a `contingencia-comandas-fallidos.fifo` |

Garantías:
- **Sin pérdidas:** nada se borra hasta procesarse, y lo que no se puede procesar queda apartado
  14 días.
- **Sin reprocesos indebidos:** cada comando y cada efecto se aplica una sola vez, aunque el mensaje
  llegue dos veces.

**Registro para diagnosticar.** Cada intento fallido deja un registro con consumidor, canal,
identificador del mensaje, número de intento, error, referencia (venta, comando o evento) y **origen**.
Se guarda 14 días en `<local>#FALLOS` (`infra/fallos.py`).

El origen se deduce del **tipo de error**, nunca del texto, y dice a quién le toca resolverlo:

| Origen | Cuándo | Quién lo resuelve |
|---|---|---|
| `proveedor` (servicio externo) | El proveedor de documentos no responde, tarda o está saturado (`ErrorProveedor`) | Esperar o contactar al proveedor |
| `aws` (infraestructura propia) | DynamoDB, SQS, SNS o S3 no responden (`ErrorInfraestructura`, errores de AWS) | Equipo técnico |
| `negocio` | Una regla del negocio rechazó la operación | El dueño o admin, según el caso |
| `codigo` | Un error no previsto del sistema | Equipo técnico (es un defecto) |

El rechazo del documento por parte del proveedor no aparece aquí: es una respuesta definitiva, sin
reintentos. Queda en el propio documento (`rechazado` y su motivo) y genera el aviso «documento
rechazado».

Las fallas de origen `proveedor` y `aws` siguen la misma política de reintentos, porque las dos son
transitorias. Se distinguen por el origen, que es el que indica a quién recurrir.

El panel de fallidos muestra el origen junto a cada mensaje apartado.

**Revisión.** En Administración → Mensajería → «Mensajes fallidos», el dueño o admin ve los mensajes
apartados de su local con el diagnóstico y elige:
- **Reprocesar**: vuelve a su cola de origen, conservando el grupo FIFO;
- **Descartar**.

Cada decisión queda registrada como evento.

## 7. Interfaz de administración

API (función `mensajeria`, solo dueño y admin, cada escritura con `X-Command-Id`):

| Operación | Ruta |
|---|---|
| Ver catálogo de canales, rutas y avisos, con el estado de cada cola | `GET /locales/{local}/mensajeria/canales` |
| Listar destinos con sus reglas y el estado de la suscripción | `GET .../mensajeria/destinos` |
| Crear destino | `POST .../mensajeria/destinos` `{nombre, tipo, correo?, avisos}` |
| Eliminar destino (suscripción y cola) | `DELETE .../mensajeria/destinos/{destino_id}` |
| Crear regla | `POST .../mensajeria/destinos/{destino_id}/reglas` `{aviso}` |
| Eliminar regla | `DELETE .../mensajeria/destinos/{destino_id}/reglas/{aviso}` |
| Ver mensajes de un destino cola (sin consumirlos) | `GET .../mensajeria/destinos/{destino_id}/mensajes` |
| Enviar aviso de prueba | `POST .../mensajeria/pruebas` `{aviso}` |
| Mensajes fallidos y errores recientes | `GET .../mensajeria/fallidos` |
| Reprocesar o descartar | `POST .../mensajeria/fallidos/{mensaje_id}/reprocesar` y `.../descartar` `{canal}` |

Pantalla: PWA → Administración → **Mensajería**, con las pestañas *Destinos y reglas*, *Canales y
rutas* y *Mensajes fallidos*.

Los canales del sistema están **protegidos**: no se crean ni borran desde la interfaz, porque los
necesita el sistema para funcionar; los define el catálogo y los crea el despliegue.

**Encapsulamiento.** Toda creación, modificación y eliminación de recursos de AWS pasa por
`GestorMensajeria` (`infra/mensajeria_aws.py`). La función solo le pide, por ejemplo, «crea la cola de
este destino» o «cambia el filtro de esta suscripción», sin conocer detalles de SNS o SQS. Las
operaciones se pueden repetir sin duplicar: el identificador del destino es el del comando, así que
reintentar no crea una segunda cola ni una segunda suscripción. Si falla el registro en la base de
datos, se deshace lo creado en AWS.

## 8. Validaciones

Cada solicitud se valida **antes** de tocar AWS. Una solicitud rechazada no crea nada.

| Validación | Respuesta |
|---|---|
| Nombre de 1 a 60 caracteres (letras, números, espacio, `-`, `_`) | 422 `NOMBRE_INVALIDO` |
| Tipo `correo` o `cola` | 422 `TIPO_DESTINO_INVALIDO` |
| Correo válido (obligatorio solo en tipo correo) | 422 `CORREO_INVALIDO` / `CAMPO_NO_CORRESPONDE` |
| Al menos un aviso, sin repetir | 422 `REGLAS_REQUERIDAS` / `REGLA_REPETIDA` |
| Aviso existente y distribuible (no una alerta técnica) | 422 `AVISO_DESCONOCIDO` / `AVISO_NO_ADMINISTRABLE` |
| Campos no permitidos | 422 `CAMPO_DESCONOCIDO` |
| Nombre o correo ya usados en el local | 409 `DESTINO_DUPLICADO` / `CORREO_YA_REGISTRADO` |
| Máximo 10 destinos por local | 409 `LIMITE_DE_DESTINOS` |
| Regla repetida, inexistente o la última del destino | 409 `REGLA_EXISTENTE` / 404 `REGLA_NO_ENCONTRADA` / 409 `ULTIMA_REGLA` |
| Canal de reproceso permitido | 422 `CANAL_INVALIDO` |
| Mensaje de otro local o ya procesado | 404 `MENSAJE_NO_ENCONTRADO` |
| Rol cajero o garzón | 403 `ROL_NO_PERMITIDO` |
| El laboratorio no da el permiso de AWS | 503 `PERMISO_AWS_DENEGADO`, indicando la operación |

Todas las respuestas son `{codigo, mensaje, detalle: {campo}}`. La PWA repite estas reglas para avisar
antes de enviar (`pwa/src/lib/mensajeria.ts`), pero el servidor siempre decide.

## 9. Cómo demostrarlo

1. **Sin AWS:**
   ```
   .venv\Scripts\python -m pytest tests/dominio/test_mensajeria_catalogo.py tests/funciones/test_mensajeria.py
   ```
   Son 44 pruebas. Cubren:
   - casos válidos e inválidos;
   - el aviso de prueba que llega solo a la cola con la regla;
   - un aviso real del procesador que sigue las mismas reglas;
   - idempotencia;
   - reproceso FIFO;
   - aislamiento entre locales;
   - el registro de fallos de `emision-dte`.
2. **En la nube, sin Google:** `python3 scripts/probar_nube.py`, sección 3. Crea dos destinos cola con
   reglas distintas, envía una prueba y comprueba que llegó solo al correcto. Luego crea y elimina una
   regla y deja todo limpio.
3. **En la nube, con la PWA:**
   1. Mensajería → Nuevo destino «Jefe de turno» (correo) con *comanda en conflicto*, y confirmar el
      correo.
   2. Nuevo destino «Contabilidad» (cola) con *documento rechazado*.
   3. Probar la distribución con *documento rechazado* → «Deben recibirlo: Contabilidad» → Ver mensajes.
4. **Error definitivo y reproceso:**
   1. Simulacro S5 de `05` (`DTE_MODO=error5xx`), y vender.
   2. Tras 5 intentos, el mensaje aparece en «Mensajes fallidos» con el diagnóstico «Proveedor no
      disponible (error5xx)».
   3. Volver a `DTE_MODO=ok` y pulsar **Reprocesar** → el documento queda emitido.
5. **Validaciones:** crear un destino sin avisos, con un correo inválido o con un nombre repetido. Se
   ve el mensaje de cada caso.

## 10. Relación con la pauta

| Criterio | Dónde se cumple |
|---|---|
| Configuración centralizada de canales y rutas | Catálogo `pos_dominio/mensajeria.py` (§1), usado por el despliegue, el procesador, la administración y las pruebas de consistencia |
| Destinos, reglas y relaciones por caso de uso | §2 y §3; mensajes de prueba con destinos esperados; pruebas de distribución |
| Separación de negocio y mensajería | §4: outbox, efectos puros, catálogo y adaptadores de infraestructura |
| Consumidores por responsabilidad | §5: cuatro consumidores, uno por responsabilidad |
| Confirmación, reintentos y errores | §6: tabla por consumidor, colas de fallidos, registro de diagnóstico, reproceso y descarte |
| Interfaz de administración | §7: API de 11 rutas y la pantalla Mensajería |
| Encapsulamiento de crear, modificar y eliminar | §7: `GestorMensajeria`, repetible y con deshacer |
| Validación de solicitudes | §8: tabla de validaciones con sus respuestas y pruebas de cada caso |
