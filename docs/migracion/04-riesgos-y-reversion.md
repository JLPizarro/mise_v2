# 04 — Riesgos de despliegue y reversión

Cada falla conocida, con cómo detectarla y cómo resolverla en la consola. Regla general: probar
**cada** pieza por separado apenas se crea (botón «Probar» con `eventos-prueba/`), antes de
conectarla con la siguiente.

## Learner Lab

| # | Falla | Cómo se detecta | Cómo resolverla |
|---|---|---|---|
| L1 | `AccessDenied`: LabRole no tiene un permiso (destino ante fallo de Streams, publicar en SNS, escribir en S3, agregar permiso de invocación) | Error rojo al guardar el disparador, o `AccessDeniedException` en los logs de la función (`ErrorInfraestructura ... causa AccessDeniedException`) | Probar cada integración sola. Alternativas si se confirma la falta de permiso: (a) **destino ante fallo de Streams denegado** → dejarlo vacío; los reintentos (10) y `Maximum age` siguen, y la alarma `pos-iterador-streams` avisa si se atasca; (b) **SNS denegado** → los avisos quedan solo en logs (nivel ERROR) y en las alarmas; (c) **permiso de invocación del API Gateway denegado** → ver A2 |
| L2 | Cuota baja de concurrencia de Lambda | Service Quotas → *Concurrent executions* menor que 15, o error al reservar concurrencia | No reservar concurrencia en ninguna función (Lambda exige dejar 10 sin reservar). `emision-dte` igual queda limitada a 2 por su disparador. Dejar anotado en `valores-despliegue.md` |
| L3 | La sesión vence a mitad del despliegue (~4 h) | La consola pide volver a iniciar sesión o muestra errores de credenciales | Lo creado se conserva. Volver a **Start Lab**, abrir AWS y seguir en el paso donde quedaste según `valores-despliegue.md`. Si una función quedó a medias, revisar su código, capa y variables antes de publicar |
| L4 | Crédito agotado: la cuenta se pierde | Aviso de presupuesto del laboratorio | Todo lo necesario para reconstruir está en el repositorio: guía `03`, `.zip` reproducibles, semilla y eventos. Los datos de DynamoDB y S3 no se recuperan. Costo esperado: ~USD 12/mes por local lleno (`costos.md`) |
| L5 | LabRole no permite administrar suscripciones o colas en tiempo de ejecución (`sns:Subscribe`, `sns:SetSubscriptionAttributes`, `sns:Unsubscribe`, `sqs:CreateQueue`, `sqs:DeleteQueue`) | Crear un destino en Mensajería responde 503 `PERMISO_AWS_DENEGADO` con la operación en `detalle`; `probar_nube.py` §3 lo muestra | Anotar la operación. Los avisos al correo de `EMAIL_AVISOS` siguen llegando (lo suscribe el despliegue con tus permisos). Para la demostración, crear la suscripción a mano en la consola de SNS con la misma política de filtro (`08-mensajeria.md` §3) |

## Lambda

| # | Falla | Cómo se detecta | Cómo resolverla |
|---|---|---|---|
| F1 | Nombre del manejador incorrecto | Test → `Runtime.HandlerNotFound` o `Unable to import module 'lambda_function'` | Code → Runtime settings → Handler = `lambda_function.lambda_handler`. El .zip debe tener `lambda_function.py` en la raíz (así lo arma `construir_capa.py`) |
| F2 | Capa sin la carpeta `python/` | Test → `No module named 'pos_dominio'` | Subir `dist/capa-pos-dominio.zip` generado por el script (la prueba `test_construir_capa.py` lo verifica). Revisar que la función tenga la capa agregada y que la capa sea **arm64** |
| F3 | Variables de entorno faltantes | Test → `VariableFaltante: Faltan variables de entorno: X` al arrancar | Configuration → Environment variables, según `02` §7 |
| F4 | Tiempo máximo o memoria insuficientes | `Task timed out after 3.00 seconds` (el valor por defecto) o `Runtime exited ... memory` | Configuration → General: valores de `02` §7. `caja` y `administracion` necesitan 512 MB por PBKDF2 |
| F5 | `Decimal` que no se serializa | `Object of type Decimal is not JSON serializable` | No debería ocurrir: toda respuesta pasa por `normalizar` (Decimal → int). Si aparece, es un defecto: revertir el alias (§R) y avisar |
| F6 | `float` rechazado por DynamoDB | `ErrorDeCodigo: float no permitido en DynamoDB (campo)` → 500 | Defecto de código: el dominio solo usa enteros y la entrada JSON se lee como `Decimal`. Revertir el alias y corregir |
| F7 | Versión de la capa no fijada o equivocada | La función usa código viejo o nuevo sin querer | Cada función apunta a una versión **concreta** de `pos-dominio` (Code → Layers). Anotar cuál en `valores-despliegue.md` |
| F8 | `SIMULAR_FALLA_DYNAMODB` olvidada en `true` | Todas las comandas responden 202 «aceptada_en_contingencia» | Quitar la variable de `pedidos`, publicar versión y mover el alias |

## API Gateway

| # | Falla | Cómo se detecta | Cómo resolverla |
|---|---|---|---|
| A1 | Ruta sin integración | 404 `{"message":"Not Found"}` o 500 en una ruta que sí existe | Routes → la ruta → Attach integration. `test_rutas_documentadas.py` garantiza que la tabla de `02` coincide con el código |
| A2 | Falta el permiso para invocar la función o el alias | 500 `Internal Server Error`; en el registro de acceso, `integrationErrorMessage` con `not authorized to perform: lambda:InvokeFunction` | Recrear la integración marcando *Grant API Gateway permission*. Si no se puede: Lambda → función → **Aliases → `vivo` → Configuration → Permissions → Resource-based policy → Add permissions**: Service **API Gateway**, Source ARN `arn:aws:execute-api:us-east-1:<cuenta>:<api-id>/*`, Action `lambda:InvokeFunction` |
| A3 | Stage sin desplegar | Los cambios no se ven; rutas nuevas responden 404 | **Deploy → `prod`**. El despliegue automático está desactivado a propósito |
| A4 | Preflight de CORS falla | En el navegador: *CORS policy: No 'Access-Control-Allow-Origin'* | CORS → origen **exacto** (con `https://`, sin `/` final), encabezados `authorization, content-type, x-command-id`. Nunca `ANY /{proxy+}`. Desplegar el stage |
| A5 | Audiencia del autorizador distinta del ID de cliente | Todas las rutas privadas dan 401 con un token válido; en el registro de acceso, `authorizerError` | Authorizer → Audience = Client ID exacto → Deploy. Mientras esté en `PENDIENTE`, el 401 es lo esperado |
| A6 | Emisor del token distinto (Google usa `https://accounts.google.com` o `accounts.google.com`) | `validar_despliegue.py` falla en el paso 0 indicando el emisor real; `obtener_token.html` lo muestra | Authorizer → Issuer URL = el valor que muestra la prueba → Deploy |
| A7 | No se puede activar el registro de acceso (rol vinculado al servicio no permitido en el laboratorio) | Error al guardar *Access logging* | Dejarlo desactivado y anotarlo. Los logs de cada función siguen teniendo `requestId`, ruta y errores |
| A8 | Ruta pública con autorizador por error (o al revés) | `/salud` o una impresora reciben 401; o una ruta privada responde sin token | Comparar con la columna JWT de `02` §6. Una ruta privada sin autorizador igual responde 401 (la función exige identidad), pero debe corregirse |

## DynamoDB

| # | Falla | Cómo se detecta | Cómo resolverla |
|---|---|---|---|
| D1 | Streams no activado antes de crear el disparador | La consola no ofrece la tabla, o el disparador queda en error | `operacion` → Exports and streams → Turn on (New image), y luego el disparador |
| D2 | Tipo de vista incorrecto (no *New image*) | `procesador-eventos` no hace nada: los registros llegan sin `NewImage` | Borrar el disparador → **Turn off** el stream → Turn on con **New image** → recrear el disparador |
| D3 | TTL sobre un atributo con otro nombre | Los `CMD#`, `EVT#` y bloqueos nunca se borran (la tabla crece) | Additional settings → TTL → atributo **`expira_en`**. El código no depende del borrado (compara la hora), así que no hay riesgo funcional |
| D4 | Transacción con más de 100 ítems | `ErrorDeCodigo: La transacción tiene N ítems` → 500 | No debería ocurrir: el dominio limita 80 líneas por tanda y por pago, y 2 medios. Si aparece, revertir y avisar |
| D5 | Índice `GSI1` de `configuracion` sin un atributo proyectado | La lista de personal o de autorizadores sale sin nombre o sin rol | Un índice no se edita: borrar `GSI1` y recrearlo con *Include* de los 6 atributos (`03` §3). Mientras se recrea, esas dos listas no responden |
| D6 | Tabla borrada por error | Todo responde 503 | Por eso está *Deletion protection* encendido. Opcional: activar **Point-in-time recovery** (Backups → Edit) en ambas tablas; con estos volúmenes cuesta centavos al mes |

## SQS

| # | Falla | Cómo se detecta | Cómo resolverla |
|---|---|---|---|
| S1 | Visibilidad menor que el tiempo máximo de la función | Mensajes procesados dos veces; aviso al crear el disparador | `dte-emision` ≥ 180 s (6 × 30 s); `contingencia-comandas.fifo` 360 s |
| S2 | Cola de fallidos de distinto tipo que la principal | La consola no deja elegirla como DLQ | FIFO con FIFO (`contingencia-comandas-fallidos.fifo`), estándar con estándar |
| S3 | Respuesta de fallos parciales activada en el disparador pero no implementada en el código, o al revés | Mensajes que fallan se borran igual, o el lote entero se reintenta | El código ya devuelve `batchItemFailures`: el disparador debe tener **Report batch item failures ✔** en los tres (Streams, `dte-emision`, contingencia) |
| S4 | Cola FIFO sin el sufijo `.fifo` | La consola no deja marcarla como FIFO, o `contingencia` falla con `MessageGroupId` | El nombre debe terminar en `.fifo` |
| S5 | Deduplicación por contenido activada en la FIFO | Dos comandos distintos con el mismo cuerpo se descartan | Desactivarla: la deduplicación usa el `command_id` |
| S6 | `MAX_RECEPCIONES` distinto del *Maximum receives* de `dte-emision` | Documentos que van a fallidos sin quedar marcados `fallido` | Ambos en 5 |

## Sitio en S3 (CloudFront no está disponible en este entorno)

| # | Falla | Cómo se detecta | Cómo resolverla |
|---|---|---|---|
| C1 | Política del bucket o *Block Public Access* impiden leer el sitio | `AccessDenied` en XML al abrir la URL | Bucket → Permissions: *Block all public access* desmarcado **y** la política de `03` §2.2. Si sigue denegado, revisar **S3 → Block Public Access settings for this account**: si está activo a nivel de cuenta, desactivarlo (solo afecta a buckets con política pública) |
| C2 | Rutas de la aplicación responden 403 o 404 | Recargar `…/caja` da `AccessDenied` o `NoSuchKey` | El endpoint REST de S3 no tiene "documento por defecto": la PWA se abre siempre en `…/index.html` y usa enrutador con `#` (`…/index.html#/caja`) |
| C3 | Caché vieja: los equipos siguen con una versión anterior | La PWA no muestra lo último publicado | Archivos con nombre versionado (los genera Vite), `index.html`, `sw.js` y `manifest.webmanifest` con `Cache-Control: no-cache`, y el service worker avisa «Hay una versión nueva» y recarga. No hay invalidación de caché que hacer |
| C4 | Bucket con puntos en el nombre | Error de certificado HTTPS | Nombre sin puntos: `pos-sitio-<cuenta>` |

## Otros

| # | Falla | Cómo se detecta | Cómo resolverla |
|---|---|---|---|
| O1 | Suscripción de SNS sin confirmar | No llegan correos | Cada destinatario debe pulsar *Confirm subscription* en el correo de AWS |
| O2 | Regla creada en *EventBridge Scheduler* en vez de regla | Error de rol al crearla | Usar **EventBridge → Rules** (`03` §10) |
| O3 | Herramienta `semilla` olvidada | Aparece en la lista de funciones | Borrarla. Es idempotente, así que ejecutarla de nuevo no daña datos, pero no debe quedar desplegada |
| O4 | Claves y códigos mock en uso real | `mock-clave-*` o los códigos `1234`/`4321` siguen activos | Administración → impresoras → **rotar clave**; cada dueño o admin define su propio código (`POST .../admin/mi-codigo`); archivar las personas `mock-*` |
| O5 | Clave de impresora rotada sigue funcionando un minuto | — | La función guarda la impresora 60 s en memoria. Esperar un minuto tras rotar |

## R. Reversión

**Código de una función** (el caso normal):
1. Lambda → función → **Aliases → `vivo` → Edit**.
2. **Version** = la anterior (anotada en `valores-despliegue.md`) → Save.
3. Efecto inmediato, sin tocar el API Gateway: las integraciones y los disparadores apuntan al alias.

**Capa**: las versiones de la capa no se modifican. Para volver atrás, la función vuelve a una
versión publicada que usaba la versión anterior de la capa (paso anterior), o se edita la capa de
`$LATEST`, se publica y se mueve el alias.

**Configuración del API Gateway** (rutas, CORS, autorizador): deshacer el cambio en la consola y
**Deploy → `prod`**. La configuración correcta está documentada en `02`.

**Datos**: no hay reversión automática de datos de negocio. Las escrituras son idempotentes por
`X-Command-Id`, así que reintentar después de revertir no duplica nada.
