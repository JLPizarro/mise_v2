# 03 — Guía de despliegue desde la consola de AWS

Pasos en orden para desplegar todo desde cero en el AWS Academy Learner Lab (región `us-east-1`),
solo con la consola web. Sin CLI, CDK, SAM, CloudFormation ni Terraform, y sin pedir credenciales.

- Valores exactos de rutas, funciones, disparadores y colas: `02-api-gateway.md`.
- Qué hacer si algo falla y cómo revertir: `04-riesgos-y-reversion.md`.
- Cómo validar: `05-validacion.md`.
- Anota cada valor que se genere (ARN, URL, versión) en `valores-despliegue.md`.

**Pendiente conocido: el ID de cliente OAuth de Google.** Todo se despliega y se prueba sin él con
datos mock (paso 12). El autorizador se crea con la audiencia `PENDIENTE`: hasta cambiarla, las rutas
privadas responden 401 a todo, así que nunca quedan abiertas. El paso 17 completa Google.

Los nombres de botones van en inglés, como aparecen con la consola en ese idioma (arriba a la
derecha: ⚙ → Language → English). Tiempo estimado: 3 a 4 horas; la sesión del laboratorio dura
unas 4, así que conviene hacerlo en dos sesiones (pasos 1–11 y 12–19). Lo creado se conserva entre
sesiones.

---

## 0. Antes de empezar (en tu computador)

1. Rama `feature/migracion-lambdas` del repositorio, actualizada.
2. Desde `POS/POS`:
   ```
   python scripts/construir_capa.py
   python scripts/generar_eventos_prueba.py
   ```
   Quedan en `dist/`: `capa-pos-dominio.zip`, `funciones/<nombre>.zip` (14) y `herramientas/semilla.zip`.
3. Opcional pero recomendado: `python scripts/validar_despliegue.py --simulado` debe terminar en
   `VALIDACIÓN COMPLETA: 13/13 pasos` (requiere `pip install -r requirements-dev.txt`).
4. Inicia el laboratorio (**Start Lab**), espera el círculo verde y abre **AWS**. Revisa que la región
   arriba a la derecha sea **N. Virginia (us-east-1)**.
5. Anota el **ID de cuenta** (menú de usuario arriba a la derecha) en `valores-despliegue.md`. En
   esta guía aparece como `<cuenta>`.

## 1. Revisar la cuota de concurrencia de Lambda

**Service Quotas → AWS services → AWS Lambda → Concurrent executions**. Anota el valor aplicado.

- Si es **1000** (lo normal): se reserva concurrencia 5 para `contingencia` en el paso 8.
- Si es **menor que 15**: Lambda exige dejar 10 sin reservar, así que **no reserves** concurrencia en
  ninguna función. Anótalo; está en el riesgo L2 de `04`.

## 2. S3: buckets del sitio y del archivo

Ambos con **Bucket type: General purpose**, región us-east-1, versionado desactivado y cifrado SSE-S3
(valor por defecto).

**2.1 `pos-archivo-<cuenta>` (privado).** Deja **Block all public access** marcado. Create bucket.

**2.2 `pos-sitio-<cuenta>` (sitio público de solo lectura).** El nombre no debe tener puntos: si los
tuviera, el certificado HTTPS de S3 no calza.
1. **Desmarca** *Block all public access* y marca la casilla de confirmación. Create bucket.
2. Bucket → **Permissions → Bucket policy → Edit** y pega (cambiando `<cuenta>`):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Sid": "LecturaPublicaDelSitio",
       "Effect": "Allow",
       "Principal": "*",
       "Action": "s3:GetObject",
       "Resource": "arn:aws:s3:::pos-sitio-<cuenta>/*"
     }]
   }
   ```
3. **Upload** `scripts/obtener_token.html`. En **Properties → Metadata** agrega
   `Cache-Control: no-cache`. Más adelante, la PWA se sube aquí mismo.
4. Comprueba en el navegador: `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/obtener_token.html`
   debe abrir la página. Si responde *AccessDenied*, ver riesgo C1 de `04`.

El sitio **no** usa "Static website hosting" (ese modo es solo HTTP). Se usa la URL REST con HTTPS de arriba.

## 3. DynamoDB: tablas

**DynamoDB → Tables → Create table**, dos veces:

| Campo | `configuracion` | `operacion` |
|---|---|---|
| Partition key | `PK` (String) | `PK` (String) |
| Sort key | `SK` (String) | `SK` (String) |
| Table settings | **Customize settings** | **Customize settings** |
| Table class | DynamoDB Standard | DynamoDB Standard |
| Capacity mode | **On-demand** | **On-demand** |
| Secondary indexes → Create global index | partition `GSI1PK` (String), sort `GSI1SK` (String), nombre **`GSI1`**, Attribute projections **Include**: `nombre`, `email`, `rol`, `estado`, `sub`, `tipo_item` | partition `GSI1PK` (String), sort `GSI1SK` (String), nombre **`GSI1`**, Attribute projections **All** |
| Deletion protection | **On** | **On** |

Cuando `operacion` esté *Active*:
1. **Exports and streams → DynamoDB stream details → Turn on → New image → Turn on stream.**
   Debe ser *New image*: para cambiar el tipo después hay que apagar el stream y borrar el disparador.
2. **Additional settings → Time to Live (TTL) → Turn on → TTL attribute name: `expira_en`** (exacto,
   en minúsculas).

`configuracion` no lleva TTL ni stream.

## 4. SQS: colas

**SQS → Create queue**, en este orden (primero las de fallidos):

| # | Nombre | Type | Visibility timeout | Message retention | Dead-letter queue |
|---|---|---|---|---|---|
| 1 | `dte-emision-fallidos` | Standard | 30 s | 14 days | — |
| 2 | `dte-emision` | Standard | **180 s** | 14 days | Enabled → `dte-emision-fallidos`, **Maximum receives 5** |
| 3 | `contingencia-comandas-fallidos.fifo` | **FIFO** | 30 s | 14 days | — |
| 4 | `contingencia-comandas.fifo` | **FIFO** | **360 s** | 14 days | Enabled → `contingencia-comandas-fallidos.fifo`, **Maximum receives 15** |
| 5 | `procesador-eventos-fallidos` | Standard | 30 s | 14 days | — |

En las dos FIFO: **Content-based deduplication desactivado** (la deduplicación usa el `command_id`).
Todo lo demás, por defecto. Anota la **URL** de las colas 2 y 4 y el **ARN** de la 5.

## 5. SNS: temas de aviso

**SNS → Topics → Create topic**, tipo **Standard**:
1. `pos-avisos-dueno`. Avisos de negocio: cierres con diferencia, documentos rechazados, conflictos
   de contingencia, autorizaciones bloqueadas.
2. `pos-alertas-tecnicas`. Alarmas de CloudWatch y documentos que agotaron sus reintentos.

En cada tema: **Create subscription → Protocol: Email → Endpoint: el correo**. Cada persona debe
abrir el correo de AWS y pulsar **Confirm subscription**; hasta entonces no recibe nada. Anota los
dos **ARN**.

## 6. CloudWatch: grupos de logs con retención (antes de crear las funciones)

Si la función crea su propio grupo, queda con retención *Never expire* y los logs se acumulan.
**CloudWatch → Logs → Log groups → Create log group**, con **Retention 1 week (7 days)**:

`/aws/lambda/salon`, `/aws/lambda/pedidos`, `/aws/lambda/caja`, `/aws/lambda/administracion`,
`/aws/lambda/reportes`, `/aws/lambda/impresion`, `/aws/lambda/contingencia`, `/aws/lambda/reservas`,
`/aws/lambda/pedidos-externos`, `/aws/lambda/procesador-eventos`, `/aws/lambda/emision-dte`,
`/aws/lambda/drenador-contingencia`, `/aws/lambda/tareas-programadas`, `/aws/lambda/semilla`
y `/aws/apigateway/pos-api`.

Si se te olvida alguno: grupo → **Actions → Edit retention setting → 1 week**.

## 7. Capa `pos-dominio`

**Lambda → Layers → Create layer**:
- Name: `pos-dominio`
- Upload a .zip file: `dist/capa-pos-dominio.zip`
- Compatible architectures: **arm64**
- Compatible runtimes: **Python 3.12**

Anota el **número de versión** (1 la primera vez). Cada función usa una versión **fija** de la capa.
Una versión nueva de la capa no cambia ninguna función hasta que se actualice explícitamente.

## 8. Funciones

Para **cada** función de la tabla de `02-api-gateway.md` §7 (las 14), con los valores de esa tabla:

1. **Lambda → Create function → Author from scratch**
   - Function name: el nombre exacto (`salon`, `pedidos`, …, `tareas-programadas`)
   - Runtime: **Python 3.12** · Architecture: **arm64**
   - **Change default execution role → Use an existing role → `LabRole`**
   - Create function
2. **Code → Upload from → .zip file** → `dist/funciones/<nombre>.zip` → Save.
   En **Runtime settings** el Handler debe decir `lambda_function.lambda_handler`.
3. **Code → Layers → Add a layer → Custom layers → `pos-dominio` → versión anotada → Add.**
4. **Configuration → General configuration → Edit:** Memory y Timeout de la tabla → Save.
5. **Configuration → Environment variables → Edit:** las variables de la tabla, con los valores de
   `valores-despliegue.md`. Por ejemplo:
   - `TABLA_OPERACION=operacion` y `TABLA_CONFIGURACION=configuracion`
   - `COLA_CONTINGENCIA_URL=https://sqs.us-east-1.amazonaws.com/<cuenta>/contingencia-comandas.fifo`

   Si falta una variable, la función falla al arrancar con el mensaje `Faltan variables de entorno: …`.
6. Solo en `contingencia`, si el paso 1 lo permite: **Configuration → Concurrency → Edit → Reserve
   concurrency: 5**.
7. **Actions → Publish new version** (descripción: `v1`). Luego **Aliases → Create alias**:
   name **`vivo`**, version **1**.

Valores especiales:
- `emision-dte`: `MAX_RECEPCIONES=5` (igual al *Maximum receives* de su cola), `DTE_MODO=ok`,
  `DTE_TASA_FALLA=1`, `DTE_LATENCIA_MS=0`.
- `pedidos-externos`: `SECRETO_WEBHOOK` = un texto aleatorio largo. En producción iría en un gestor
  de secretos; en el laboratorio se usa una variable porque es temporal.
- **Nunca** pongas `SIMULAR_FALLA_DYNAMODB` salvo durante el simulacro de `05`.

## 9. Disparadores (sobre el alias `vivo`)

Los disparadores se agregan **en el alias**, no en la función (`$LATEST`). Así, revertir el alias
también revierte el código que consume eventos. Abre la función → **Aliases → `vivo` → Add trigger**.

**9.1 `procesador-eventos` ← DynamoDB Streams**
- Source: **DynamoDB** · Table: `operacion` · Batch size: **100** · Starting position: **Latest**
- Batch window: **1**
- Additional settings:
  - On-failure destination: **SQS** → ARN de `procesador-eventos-fallidos`
  - Retry attempts: **10** · Maximum age of record: **3600**
  - **Split batch on error: ✔** · **Report batch item failures: ✔**
- Filter criteria (una sola línea):
  ```json
  {"eventName":["INSERT"],"dynamodb":{"Keys":{"SK":{"S":[{"prefix":"EVT#"}]}}}}
  ```

**9.2 `emision-dte` ← SQS `dte-emision`**
- Batch size **5** · Batch window **0** · **Report batch item failures: ✔** · **Maximum concurrency: 2**

**9.3 `drenador-contingencia` ← SQS `contingencia-comandas.fifo`**
- Batch size **10** · **Report batch item failures: ✔**

Si al guardar aparece *AccessDenied* (por ejemplo, con el destino ante fallo), ver riesgo L1 de `04`.

## 10. Regla programada de `tareas-programadas`

**EventBridge → Buses → Rules → Create rule.** Si la consola ofrece *EventBridge Scheduler*, elige
la opción de **regla** (*Continue to create rule*): Scheduler exige un rol propio y LabRole no puede.
- Name: `pos-tareas-programadas` · Rule type: **Schedule** · `rate(5 minutes)`
- Target: **AWS service → Lambda function → `tareas-programadas`**, Configure version/alias → **Alias: `vivo`**
- Create rule.

## 11. Datos de prueba (herramienta `semilla`)

1. Crea la función **`semilla`** igual que en el paso 8:
   - código `dist/herramientas/semilla.zip`, capa `pos-dominio`;
   - **Memory 512 MB, Timeout 60 s**;
   - variables `TABLA_OPERACION=operacion` y `TABLA_CONFIGURACION=configuracion`;
   - opcional: `EMAIL_DUENO_REAL=<email del dueño>`, que deja su invitación lista para cuando exista
     el ID de cliente de Google;
   - no publiques versión ni crees alias.
2. **Test → Create new event** con `{}` → **Test**. Respuesta esperada:
   `{"creados": ..., "ya_existian": 0, "tenant_id": "demo", "local_id": "local_01"}`.
   Si la ejecutas de nuevo, `creados` es 0: no pisa nada.
3. **Borra la función `semilla`** (Actions → Delete). No debe quedar desplegada.

Datos cargados: cliente `demo`, local `local_01` "MISE Centro", 12 mesas, 2 sectores, 10 productos,
cocina y barra, impresoras `imp_cocina`, `imp_barra` e `imp_caja`, y seis personas `mock-*`. Los
códigos y claves mock están en `05-validacion.md`.

## 12. Probar cada función con datos mock (sin Google)

Sigue `eventos-prueba/README.md` **en orden**. En cada función: **Aliases → `vivo` → Test → Create
new event**, pega el JSON y compara el código HTTP con el de la tabla. Esto detecta manejador
incorrecto, capa mal armada, variables faltantes, permisos de LabRole y tiempo máximo insuficiente,
función por función, antes de exponer la API.

## 13. API Gateway

**13.1 API y stage**
1. **API Gateway → Create API → HTTP API → Build.** API name: **`pos-api`**. No agregues
   integraciones todavía → Next → no agregues rutas → Next.
2. En *Stages*: si aparece `$default` con auto-deploy, **elimínalo**. Agrega un stage **`prod`**
   con **Auto-deploy desactivado** → Next → Create.

**13.2 Autorizador** — **Authorization → Manage authorizers → Create**
- Type **JWT** · Name **`google-id-token`** · Identity source **`$request.header.Authorization`**
- Issuer URL **`https://accounts.google.com`** · Audience **`PENDIENTE`** (se cambia en el paso 17)

**13.3 Integraciones** — **Integrations → Manage integrations → Create**, una por función de la API
(`salon`, `pedidos`, `caja`, `administracion`, `reportes`, `impresion`, `contingencia`, `reservas`,
`pedidos-externos`, `mensajeria`):
- Integration type **Lambda function** · AWS Region **us-east-1**
- Lambda function: el ARN **del alias**: `arn:aws:lambda:us-east-1:<cuenta>:function:salon:vivo`
- **Grant API Gateway permission to invoke your Lambda function: ✔**
- Advanced settings: **Payload format version 2.0**

**13.4 Rutas** — **Routes → Create**, las **59** de la tabla de `02-api-gateway.md` §6, con el método
y la ruta exactos (por ejemplo `POST` y `/locales/{local_id}/pedidos`). En cada ruta:
1. **Attach integration → Choose an existing integration** → la función de la tabla.
2. Si la columna JWT dice **sí**: **Attach authorization → `google-id-token`**.

No crees `ANY /{proxy+}`. Revisa que `GET /salud`, las 3 de `/impresion`, las 2 de `/publico` y la de
`/webhooks` queden **sin** autorizador.

**13.5 CORS** — **CORS → Configure**
- Access-Control-Allow-Origin: `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com` y `http://localhost:8000`
- Allow-Headers: `authorization`, `content-type`, `x-command-id`
- Allow-Methods: `GET`, `POST`, `PATCH`, `DELETE`
- Expose-Headers: `x-comando-repetido`
- Max-Age: `600` · Allow-Credentials: **No**

**13.6 Límites de tasa** — **Protect → Throttling → stage `prod`**
- Default route throttling: Rate **50**, Burst **100**
- Por ruta: las 2 `/publico/...` con 2/5, las 3 `/impresion/...` con 20/40, `POST /webhooks/...` con 5/10

**13.7 Registro de acceso** — **Monitor → Logging → `prod` → Edit**
- Access logging: **on** · Log destination: ARN del grupo `/aws/apigateway/pos-api`
- Log format: el JSON de `02-api-gateway.md` §5

**13.8 Desplegar** — **Deploy → stage `prod`**. Anota la **Invoke URL**
(`https://<id>.execute-api.us-east-1.amazonaws.com/prod`: con un stage con nombre, la URL termina en
`/prod`).

Comprobación inmediata, en el navegador:
- `<Invoke URL>/salud` debe responder `{"estado":"ok",...}`.
- `<Invoke URL>/yo` debe responder **401**: el autorizador está activo y con audiencia pendiente.

## 14. Probar la API con el simulador de impresora (sin Google)

Las rutas de impresión no usan Google, así que ya se pueden probar de punta a punta (`05-validacion.md` §6):
```
$env:POS_CLAVE_IMPRESORA = "mock-clave-cocina"
python scripts/simulador_impresora.py --api <Invoke URL> --una-vez
```
Si el flujo de eventos de prueba del paso 12 dejó trabajos pendientes, los imprime en la terminal.

## 15. Athena (archivo histórico)

1. **Athena → Query editor → Settings → Manage → Location of query result:**
   `s3://pos-archivo-<cuenta>/athena-resultados/` → Save.
2. Abre `infra/athena/eventos.sql`, reemplaza `<BUCKET_ARCHIVO>` por `pos-archivo-<cuenta>` y
   ejecuta las dos sentencias (**Run**), una por una.
3. Prueba, con la fecha de hoy:
   `SELECT tipo, count(*) FROM pos.eventos WHERE tenant='demo' AND fecha = current_date GROUP BY tipo;`

## 16. Alarmas de CloudWatch

**CloudWatch → Alarms → Create alarm**. Todas con **Datapoints to alarm 1 de 1**, **Treat missing
data: not breaching**, y acción **In alarm → SNS → `pos-alertas-tecnicas`**.

| Nombre | Métrica (Select metric) | Estadística / periodo | Condición |
|---|---|---|---|
| `pos-fallidos-dte` | SQS › Queue Metrics › `dte-emision-fallidos` › ApproximateNumberOfMessagesVisible | Maximum / 5 min | ≥ 1 |
| `pos-fallidos-contingencia` | SQS › `contingencia-comandas-fallidos.fifo` › ApproximateNumberOfMessagesVisible | Maximum / 5 min | ≥ 1 |
| `pos-fallidos-eventos` | SQS › `procesador-eventos-fallidos` › ApproximateNumberOfMessagesVisible | Maximum / 5 min | ≥ 1 |
| `pos-dte-atrasado` | SQS › `dte-emision` › ApproximateAgeOfOldestMessage | Maximum / 5 min | > 900 |
| `pos-contingencia-atrasada` | SQS › `contingencia-comandas.fifo` › ApproximateAgeOfOldestMessage | Maximum / 1 min | > 300 |
| `pos-errores-lambda` | Lambda › **Across All Functions** › Errors | Sum / 5 min | > 0 |
| `pos-limitaciones-lambda` | Lambda › **Across All Functions** › Throttles | Sum / 5 min | > 0 |
| `pos-iterador-streams` | Lambda › By Function Name › `procesador-eventos` › IteratorAge | Maximum / 1 min | > 60000 |
| `pos-api-5xx` | ApiGateway › ApiId, Stage (`pos-api`, `prod`): **5xx** (m1) y **Count** (m2), Sum / 5 min → **Add math** `100 * m1 / m2` | expresión | > 1 |

En `pos-api-5xx`, selecciona la **expresión** como métrica de la alarma, no m1 ni m2.

## 17. Google (cuando exista el ID de cliente) — PENDIENTE

1. Google Cloud Console → **APIs & Services → OAuth consent screen**: External, modo *Testing*, con
   los correos del equipo como *Test users*.
2. **Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized JavaScript origins: `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com` y
     `http://localhost:8000`
   - Sin redirect URIs: el flujo para navegador no las usa.
3. Copia el **Client ID** (termina en `.apps.googleusercontent.com`). No hace falta el secreto.
4. API Gateway → `pos-api` → **Authorization → `google-id-token` → Edit → Audience** = el Client ID →
   Save → **Deploy → `prod`**.
5. Abre `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/obtener_token.html`, pega el Client ID e
   inicia sesión con el email que pusiste en `EMAIL_DUENO_REAL`. Revisa el **emisor** que muestra la
   página: si no es `https://accounts.google.com`, cambia el Issuer del autorizador por ese valor
   exacto y vuelve a desplegar.
6. Copia el token y ejecuta `validar_despliegue.py` en modo real (`05-validacion.md` §3).

Si no pusiste `EMAIL_DUENO_REAL` en la semilla, vuelve a crear la función `semilla` con esa
variable y ejecútala otra vez: no pisa nada, solo agrega la invitación. Después bórrala.

## 18. Validación completa

`05-validacion.md`: idempotencia, simulacros de documento tributario y contingencia, y alarmas.

## 19. Cada nuevo despliegue de código

1. `python scripts/construir_capa.py`.
2. Si cambió la capa: **Layers → `pos-dominio` → Create version** → actualiza la versión de la capa
   en cada función afectada.
3. Función → **Upload from .zip** → **Test** en `$LATEST` con su evento de `eventos-prueba`.
4. **Publish new version** → **Aliases → `vivo` → Edit → Version: la nueva** → Save.
5. Si algo falla: **revertir el alias** a la versión anterior (`04-riesgos-y-reversion.md` §R).

La API apunta al alias, así que no hace falta volver a desplegar el stage al cambiar código. Solo
se despliega el stage al cambiar rutas, el autorizador, CORS o los límites de tasa.

## Reconstruir si el laboratorio se reinicia o se acaba el crédito

Todo lo necesario está en este repositorio. Repite esta guía desde el paso 0. Lo único que no se
puede recuperar son los datos de DynamoDB y S3: se parte de nuevo con la semilla.
