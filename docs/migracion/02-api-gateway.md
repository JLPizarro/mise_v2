# 02 — API Gateway y configuración de las funciones

Valores exactos para copiar en la consola (región `us-east-1`). Los pasos en orden están en
`03-guia-consola.md`. La prueba `tests/funciones/test_rutas_documentadas.py` compara la tabla de
rutas de este documento con las rutas que atiende el código: si alguien agrega una ruta y no la
documenta (o al revés), la prueba falla.

## 1. La API

| Campo | Valor |
|---|---|
| Tipo | HTTP API |
| Nombre | `pos-api` |
| Stage | `prod` |
| Despliegue automático | **Desactivado**. Un cambio a medias no queda publicado; se publica con «Deploy» después de validar |
| Formato de carga de las integraciones | **2.0** |
| Destino de cada integración | el alias **`vivo`** de la función (`arn:aws:lambda:us-east-1:<cuenta>:function:<nombre>:vivo`), nunca `$LATEST` |

Rutas **explícitas**. No se usa `ANY /{proxy+}`: con autorizador, captura las peticiones
`OPTIONS` del navegador y rompe CORS. Las rutas con parámetros (`{recurso}`, `{id}`) son explícitas
igual: no capturan `OPTIONS`.

## 2. Autorizador JWT

| Campo | Valor |
|---|---|
| Nombre | `google-id-token` |
| Tipo | JWT |
| Fuente de identidad | `$request.header.Authorization` |
| Emisor (issuer) | `https://accounts.google.com` |
| Audiencia | el **ID de cliente OAuth web** de Google Cloud (`xxxxxxxx.apps.googleusercontent.com`). **Pendiente**: mientras no exista, se crea con `PENDIENTE`; así todas las rutas privadas responden 401 y nunca quedan abiertas |

Se asigna a **todas las rutas excepto** `GET /salud`, `/impresion/*`, `/webhooks/*` y `/publico/*`
(columna «JWT» de la tabla).

Google documenta dos emisores posibles (`https://accounts.google.com` y `accounts.google.com`). El
autorizador acepta uno solo. `scripts/validar_despliegue.py` verifica el emisor real de los tokens
que recibe la PWA antes de todo lo demás (riesgo en `04-riesgos-y-reversion.md`).

## 3. CORS

| Campo | Valor |
|---|---|
| Access-Control-Allow-Origin | el origen exacto del sitio: `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com` (sin `/` final) y, para las pruebas con `scripts/obtener_token.html`, `http://localhost:8000` |
| Access-Control-Allow-Headers | `authorization`, `content-type`, `x-command-id` |
| Access-Control-Allow-Methods | `GET`, `POST`, `PATCH`, `DELETE` |
| Access-Control-Expose-Headers | `x-comando-repetido` |
| Access-Control-Max-Age | `600` |
| Access-Control-Allow-Credentials | **No** |

## 4. Límites de tasa

En **Protect → Throttling** del stage `prod`:

| Alcance | Tasa (req/s) | Ráfaga |
|---|---|---|
| Por defecto del stage (todas las rutas) | 50 | 100 |
| Rutas `/publico/...` (las 2) | 2 | 5 |
| Rutas `/impresion/...` (las 3) | 20 | 40 |
| `POST /webhooks/...` | 5 | 10 |

## 5. Registro de acceso

Grupo de CloudWatch `/aws/apigateway/pos-api`, **retención 7 días**. Formato (una línea, JSON):

```json
{"requestId":"$context.requestId","routeKey":"$context.routeKey","status":"$context.status","integrationErrorMessage":"$context.integrationErrorMessage","authorizerError":"$context.authorizer.error","responseLatency":"$context.responseLatency","integrationLatency":"$context.integrationLatency","ip":"$context.identity.sourceIp","requestTime":"$context.requestTime"}
```

No incluye encabezados ni cuerpos: nunca se registra `Authorization`.

## 6. Rutas

Roles: `D` dueño · `A` admin · `C` cajero · `G` garzón. «Público» = sin autorizador JWT (las valida
la propia función o no requieren identidad). Toda ruta de escritura exige `X-Command-Id` (ULID),
salvo las públicas.

| Ruta | Función | JWT | Roles |
|---|---|---|---|
| `GET /salud` | salon | no | público |
| `GET /yo` | salon | sí | cualquiera con membresía |
| `GET /locales/{local_id}/salon` | salon | sí | D A C G |
| `GET /locales/{local_id}/catalogo` | salon | sí | D A C G |
| `POST /locales/{local_id}/mesas/{mesa_id}/bloqueo` | salon | sí | D A C |
| `POST /locales/{local_id}/mesas/{mesa_id}/garzon` | salon | sí | D A C |
| `POST /locales/{local_id}/pedidos` | pedidos | sí | D A C G |
| `GET /locales/{local_id}/pedidos/{pedido_id}` | pedidos | sí | D A C G |
| `POST /locales/{local_id}/pedidos/{pedido_id}/items` | pedidos | sí | D A C G |
| `PATCH /locales/{local_id}/pedidos/{pedido_id}/items/{item_id}` | pedidos | sí | D A C G |
| `DELETE /locales/{local_id}/pedidos/{pedido_id}/items/{item_id}` | pedidos | sí | D A C G |
| `POST /locales/{local_id}/pedidos/{pedido_id}/enviar` | pedidos | sí | D A C G |
| `POST /locales/{local_id}/pedidos/{pedido_id}/precuenta` | pedidos | sí | D A C G |
| `POST /locales/{local_id}/pedidos/{pedido_id}/reabrir` | pedidos | sí | D A C G |
| `POST /locales/{local_id}/pedidos/{pedido_id}/pagos` | caja | sí | D A C |
| `POST /locales/{local_id}/pedidos/{pedido_id}/finalizar` | caja | sí | D A C |
| `GET /locales/{local_id}/caja/turno` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/turnos` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/turnos/{turno_id}/conteo` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/turnos/{turno_id}/conciliacion` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/turnos/{turno_id}/cerrar` | caja | sí | D A C |
| `GET /locales/{local_id}/caja/pendientes` | caja | sí | D A C |
| `GET /locales/{local_id}/caja/autorizadores` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/retiros` | caja | sí | D A C (autoriza D o A con su código) |
| `GET /locales/{local_id}/caja/retiros` | caja | sí | D A C |
| `GET /locales/{local_id}/caja/documentos` | caja | sí | D A C |
| `GET /locales/{local_id}/caja/documentos/{venta_id}` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/documentos/{venta_id}/reimprimir` | caja | sí | D A C |
| `GET /locales/{local_id}/caja/conflictos` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/conflictos/{conflicto_id}/resolver` | caja | sí | D A C |
| `GET /locales/{local_id}/caja/impresiones-retenidas` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/impresiones-retenidas/{trabajo_id}/liberar` | caja | sí | D A C |
| `POST /locales/{local_id}/caja/impresiones-retenidas/{trabajo_id}/descartar` | caja | sí | D A C |
| `GET /locales/{local_id}/admin/{recurso}` | administracion | sí | D A |
| `POST /locales/{local_id}/admin/{recurso}` | administracion | sí | D A (rol dueño: solo D) |
| `PATCH /locales/{local_id}/admin/{recurso}/{id}` | administracion | sí | D A (rol dueño: solo D) |
| `DELETE /locales/{local_id}/admin/{recurso}/{id}` | administracion | sí | D A |
| `POST /locales/{local_id}/admin/{recurso}/{id}/{accion}` | administracion | sí | D A |
| `GET /locales/{local_id}/mensajeria/canales` | mensajeria | sí | D A |
| `GET /locales/{local_id}/mensajeria/destinos` | mensajeria | sí | D A |
| `POST /locales/{local_id}/mensajeria/destinos` | mensajeria | sí | D A |
| `DELETE /locales/{local_id}/mensajeria/destinos/{destino_id}` | mensajeria | sí | D A |
| `POST /locales/{local_id}/mensajeria/destinos/{destino_id}/reglas` | mensajeria | sí | D A |
| `DELETE /locales/{local_id}/mensajeria/destinos/{destino_id}/reglas/{aviso}` | mensajeria | sí | D A |
| `GET /locales/{local_id}/mensajeria/destinos/{destino_id}/mensajes` | mensajeria | sí | D A |
| `POST /locales/{local_id}/mensajeria/pruebas` | mensajeria | sí | D A |
| `GET /locales/{local_id}/mensajeria/fallidos` | mensajeria | sí | D A |
| `POST /locales/{local_id}/mensajeria/fallidos/{mensaje_id}/reprocesar` | mensajeria | sí | D A |
| `POST /locales/{local_id}/mensajeria/fallidos/{mensaje_id}/descartar` | mensajeria | sí | D A |
| `GET /locales/{local_id}/reportes/turnos` | reportes | sí | D A |
| `GET /locales/{local_id}/reportes/turnos/{turno_id}` | reportes | sí | D A |
| `GET /locales/{local_id}/reportes/dias/{fecha}` | reportes | sí | D A |
| `POST /impresion/{tenant_id}/{local_id}/{impresora_id}` | impresion | no | impresora (Basic) |
| `GET /impresion/{tenant_id}/{local_id}/{impresora_id}` | impresion | no | impresora (Basic) |
| `DELETE /impresion/{tenant_id}/{local_id}/{impresora_id}` | impresion | no | impresora (Basic) |
| `POST /contingencia/comandas` | contingencia | sí | D A C G (se autoriza al drenar) |
| `GET /publico/{tenant_id}/{local_id}/reservas/disponibilidad` | reservas | no | público |
| `POST /publico/{tenant_id}/{local_id}/reservas` | reservas | no | público |
| `POST /webhooks/{plataforma}/{tenant_id}/{local_id}` | pedidos-externos | no | firma HMAC |

Recursos de `administracion`: `sectores`, `mesas`, `productos`, `cuartos`, `impresoras`,
`materias-primas`, `recetas`, `configuracion` (con id `local`), `personal`, `invitaciones`
(solo `DELETE`), `mi-codigo` (solo `POST`), `estaciones`. Acción: `impresoras/{id}/rotar-clave`.

Rutas de `mensajeria`: administración de destinos, reglas de distribución y mensajes fallidos. El detalle
funcional está en `08-mensajeria.md`.

## 7. Configuración de cada función

Todas: **Python 3.12**, **arm64**, rol **LabRole**, manejador **`lambda_function.lambda_handler`**,
capa `pos-dominio` en una versión **fija** (no "la última"), alias `vivo` apuntando a una versión
publicada. `LOG_LEVEL` es opcional (por defecto `WARNING`).

| Función | Tiempo máx. | Memoria | Variables de entorno | Disparador |
|---|---|---|---|---|
| `salon` | 10 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION` | API |
| `pedidos` | 10 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION`, `COLA_CONTINGENCIA_URL` | API |
| `caja` | 10 s | **512 MB** | `TABLA_OPERACION`, `TABLA_CONFIGURACION` | API |
| `administracion` | 10 s | **512 MB** | `TABLA_OPERACION`, `TABLA_CONFIGURACION` | API |
| `reportes` | 10 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION` | API |
| `impresion` | 10 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION`, `IMPRESION_ASCII` (opcional) | API |
| `contingencia` | 10 s | 128 MB | `COLA_CONTINGENCIA_URL` | API · **concurrencia reservada 5** |
| `reservas` | 10 s | 128 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION` | API |
| `pedidos-externos` | 10 s | 128 MB | `SECRETO_WEBHOOK`, `TABLA_OPERACION`, `TABLA_CONFIGURACION` | API |
| `mensajeria` | 15 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION`, `TEMA_DUENO_ARN`, `ESPERA_SQS_SEGUNDOS` (opcional, por defecto 1) | API |
| `procesador-eventos` | 60 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION`, `BUCKET_ARCHIVO`, `COLA_DTE_URL`, `TEMA_DUENO_ARN`, `TEMA_ALERTAS_ARN` | Streams de `operacion` |
| `emision-dte` | 30 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION`, `COLA_DTE_URL`, `MAX_RECEPCIONES`=`5`, `DTE_MODO`=`ok`, `DTE_TASA_FALLA`=`1`, `DTE_LATENCIA_MS`=`0` | SQS `dte-emision` |
| `drenador-contingencia` | 30 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION` | SQS `contingencia-comandas.fifo` |
| `tareas-programadas` | 60 s | 256 MB | `TABLA_OPERACION`, `TABLA_CONFIGURACION`, `COLA_DTE_URL`, `TEMA_DUENO_ARN`, `TEMA_ALERTAS_ARN` | EventBridge `rate(5 minutes)` |

`caja` y `administracion` llevan 512 MB porque verificar o definir un código de autorización usa
PBKDF2 de 200.000 iteraciones, y en Lambda la CPU crece con la memoria.

`SIMULAR_FALLA_DYNAMODB=true` existe solo para el simulacro de contingencia en `pedidos`. Nunca debe
quedar puesta.

Herramienta temporal `semilla` (no es parte de la arquitectura): Python 3.12, arm64, LabRole, capa
`pos-dominio`, 512 MB, 60 s, `TABLA_OPERACION`, `TABLA_CONFIGURACION` y `EMAIL_DUENO_REAL` (opcional).
Se ejecuta una vez y se borra (`03` §11).

## 8. Disparadores

Todos se crean **sobre el alias `vivo`** (no sobre `$LATEST`): revertir el alias revierte también el
código que consume eventos.

| Disparador | Valores |
|---|---|
| Streams `operacion` → `procesador-eventos` | posición inicial `LATEST`; lote 100; ventana de lote 1 s; **dividir el lote ante error: sí**; **reintentos: 10**; **antigüedad máxima del registro: 3600 s**; **destino ante fallo: cola SQS estándar `procesador-eventos-fallidos`**; **informar fallos de elementos del lote: sí**; filtro: `{"eventName":["INSERT"],"dynamodb":{"Keys":{"SK":{"S":[{"prefix":"EVT#"}]}}}}` |
| SQS `dte-emision` → `emision-dte` | lote 5; ventana 0; **informar fallos de elementos del lote: sí**; **concurrencia máxima: 2** (el mínimo que permite Lambda; respeta el límite del proveedor) |
| SQS `contingencia-comandas.fifo` → `drenador-contingencia` | lote 10; **informar fallos de elementos del lote: sí** |
| EventBridge `pos-tareas-programadas` → `tareas-programadas` | regla programada (no Scheduler), expresión `rate(5 minutes)` |

## 9. Colas

La fuente de esta tabla es el catálogo `lambdas/capa/python/pos_dominio/mensajeria.py`: `desplegar.sh` crea las
colas desde él y una prueba comprueba que esta tabla dice lo mismo.

| Cola | Tipo | Visibilidad | Retención | Fallidos |
|---|---|---|---|---|
| `dte-emision` | estándar | **180 s** (6 × 30 s de `emision-dte`) | 14 días | `dte-emision-fallidos` (estándar), **5 recepciones** |
| `dte-emision-fallidos` | estándar | 30 s | 14 días | — |
| `contingencia-comandas.fifo` | **FIFO**, sin deduplicación por contenido | **360 s** | 14 días | `contingencia-comandas-fallidos.fifo` (**FIFO**), **15 recepciones** (≈ 90 min de reintentos) |
| `contingencia-comandas-fallidos.fifo` | **FIFO** | 30 s | 14 días | — |
| `procesador-eventos-fallidos` | estándar | 30 s | 14 días | — (destino ante fallo del Streams) |

La cola de fallidos debe ser del mismo tipo que la principal (FIFO con FIFO). El nombre de una cola
FIFO debe terminar en `.fifo`.
