# 05 — Validación

Del menos al más costoso: pruebas locales (sin AWS), eventos en la consola (sin Google), validación
de punta a punta y simulacros.

## Datos mock (de la herramienta `semilla`)

Solo para pruebas. Antes de un uso real, rotar las claves y archivar a las personas `mock-*`
(`04` O4).

| Persona (`sub`) | Rol | Código de autorización |
|---|---|---|
| `mock-dueno` | dueño | `1234` |
| `mock-admin` | admin | `4321` |
| `mock-cajero` | cajero | — |
| `mock-garzon`, `mock-garzon2` | garzón | — |
| `mock-cocina` | cocina | — |

| Impresora | Cuarto | Clave CloudPRNT |
|---|---|---|
| `imp_cocina` | Cocina (fondos, entradas, postres) | `mock-clave-cocina` |
| `imp_barra` | Barra (bebidas) | `mock-clave-barra` |
| `imp_caja` | Caja (boletas y facturas) | `mock-clave-caja` |

Cliente `demo`, local `local_01` "MISE Centro", mesas `m01` a `m12` (`m09`–`m12` en terraza),
productos con IDs legibles (`pizza`, `bebida`, `lomo`, `cafe`…).

## 1. Pruebas locales automatizadas

Desde `POS/POS`, con Python 3.11 o superior:
```
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -o addopts=""
```

| Carpeta | Qué prueba |
|---|---|
| `tests/caracterizacion` | El comportamiento del POS local, sobre una copia congelada de su código y valores de referencia del frontend |
| `tests/dominio` | Reglas puras (división, propina, umbral contra el local), arquitectura de la capa, armado del `.zip` |
| `tests/integracion` | Operaciones contra DynamoDB simulado (moto): transacciones, idempotencia, carreras, clasificación de errores |
| `tests/funciones` | Las 14 funciones con eventos reales del API Gateway, SQS, Streams y EventBridge; tabla de rutas contra `02`; flujo de `eventos-prueba`; `validar_despliegue.py --simulado` |

Validación simulada de punta a punta, sin AWS ni Google:
```
.venv\Scripts\python scripts/validar_despliegue.py --simulado
```
Resultado esperado: `VALIDACIÓN COMPLETA: 13/13 pasos`.

## 2. Eventos de prueba en la consola

`eventos-prueba/README.md` tiene **43 eventos en orden**, con el código HTTP esperado y qué comprobar.
Cubre 13 de las 14 funciones (`mensajeria` se prueba con `probar_nube.py` §3 y `validar_despliegue.py`), incluida una reaplicación de contingencia que termina en conflicto. La
prueba `test_eventos_prueba.py` ejecuta exactamente ese flujo sobre la semilla, así que si la
consola da otro resultado, el problema está en el despliegue y no en el código.

Cómo leer el resultado de una función de la API en la consola: el campo `statusCode` es el código
HTTP y `body` es la respuesta. Los errores siempre traen `codigo`, `mensaje` y `requestId`.

## 3. Validación del despliegue (`scripts/validar_despliegue.py`)

Recorre: token → `/salud` → `/yo` → plano y carta → abrir mesa → idempotencia → enviar tanda →
impresión CloudPRNT → turno → precuenta, cobro y finalizar → documento emitido (espera el flujo
asíncrono) → cierre de turno sin diferencia → reporte del turno con la venta.

**Sin Google** (ya disponible): `--simulado` (§1).

**Contra AWS** (cuando exista el ID de cliente; `03` §17):
```
$env:POS_ID_TOKEN = "<ID token de obtener_token.html>"
$env:POS_CLAVE_IMPRESORA = "mock-clave-cocina"
python scripts/validar_despliegue.py --api https://<id>.execute-api.us-east-1.amazonaws.com/prod --local local_01
```
- Usa la cuenta del dueño: la invitación de `EMAIL_DUENO_REAL` la vincula al primer ingreso.
- El **paso 0 verifica el emisor real del token**. Si no coincide con el del autorizador, indica el
  valor exacto que hay que poner (`04` A6).
- Solo cierra el turno si lo abrió la propia validación; si ya había uno abierto, lo deja como estaba.

## 4. Idempotencia

| Dónde | Qué comprueba |
|---|---|
| `validar_despliegue.py`, paso «idempotencia» | El mismo `X-Command-Id` enviado dos veces devuelve la misma respuesta, con el encabezado `x-comando-repetido: true`, y el pedido queda con **un** ítem |
| Consola | Ejecutar dos veces `pedidos/02-agregar-pizza-xl.json`: la segunda respuesta trae `x-comando-repetido: true` en `headers` y `05-ver-pedido` sigue con total 16.500 |
| Contingencia | `drenador-contingencia/01-abrir-mesa-m07.json` usa el mismo `command_id` que `contingencia/01-comanda.json`: aunque el comando llegue dos veces (cola y consola), la mesa 7 tiene un solo pedido |

## 5. Simulacros

Cada simulacro que cambia una variable de entorno se hace **publicando una versión y moviendo el
alias**, y se termina **devolviendo el alias a la versión normal**. Así cada simulacro sirve también
para practicar la reversión (`04` §R).

| # | Simulacro | Cómo | Resultado esperado |
|---|---|---|---|
| S1 | Falla de DynamoDB forzada en `pedidos` | `pedidos` → variable `SIMULAR_FALLA_DYNAMODB=true` → publicar versión → mover `vivo`. Ejecutar `pedidos/01-abrir-mesa.json` con otro `x-command-id`, mesa `m06` y **sin** el campo `pedido_id` del cuerpo | `202 {"estado":"aceptada_en_contingencia"}`. El mensaje entra en `contingencia-comandas.fifo` y `drenador-contingencia` lo aplica en segundos (su DynamoDB funciona): la mesa 6 queda ocupada con `origen: "contingencia"`. Si la tanda se envía así, la impresión queda en `caja/impresiones-retenidas`. Al final, alias de vuelta. **Sin duplicados**: repetir el mismo comando no crea otro pedido |
| S2 | `pedidos` sin capacidad (la PWA pasa a contingencia) | `pedidos` → Configuration → Concurrency → **Reserve concurrency 0** (no requiere cuota) | Las rutas de `pedidos` responden **5xx** (límite de Lambda). El cliente envía la comanda a `POST /contingencia/comandas` (`contingencia/01-comanda.json` con otro `x-command-id`, mesa `m08` y sin `pedido_id`) → `202`, y el drenador la aplica. Al final: **Remove** la concurrencia reservada |
| S3 | `DTE_MODO=ok` | Valor normal | `caja/06-documento.json` → `emitido` con folio en segundos; trabajo `DTE-<venta>` pendiente en `imp_caja` |
| S4 | `DTE_MODO=lento` | `emision-dte` con `DTE_MODO=lento` (`DTE_LATENCIA_MS` 3000 por defecto) | Igual que S3, unos 3 s más tarde |
| S5 | `DTE_MODO=timeout`, `error5xx` o `limite429` | Cambiar `DTE_MODO` (y opcionalmente `DTE_TASA_FALLA=0.5` para fallas parciales) | El cobro **no se bloquea**. El documento queda `enviando`; los logs muestran `falla transitoria del proveedor` con esperas crecientes (≈ 30, 60, 120, 240 s). En la **5.ª recepción** queda `fallido`, el mensaje pasa a `dte-emision-fallidos`, salta la alarma `pos-fallidos-dte` y llega un correo a alertas técnicas. Con `DTE_TASA_FALLA=0.5`, la mayoría termina emitida tras uno o dos reintentos |
| S6 | `DTE_MODO=rechazo` | Cambiar `DTE_MODO` | `rechazado` con su motivo, **sin reintentos**; correo al dueño «documento tributario rechazado» |
| S7 | Reenvío desde la cola de fallidos | Tras S5: `DTE_MODO=ok` (alias de vuelta) → SQS → `dte-emision-fallidos` → **Start DLQ redrive** → *Redrive to source queue* | El documento `fallido` se intenta de nuevo y queda `emitido` **con el mismo folio** si ya tenía uno. La alarma vuelve a OK cuando la cola de fallidos queda vacía |
| S8 | Reaplicación con conflicto | `drenador-contingencia/02-agregar-a-mesa-ya-cobrada.json` | `batchItemFailures: []` (no se reintenta). `caja/13-conflictos.json` muestra `PEDIDO_CERRADO`; correo al dueño «comanda en conflicto». `POST .../caja/conflictos/{id}/resolver` con `{"resolucion":"resuelto"}` lo cierra |
| S9 | Corte de red en el PC de caja | Con la PWA: DevTools → Network → **Offline** en la estación de caja → registrar comandas → recargar (sigue funcionando) → **No throttling** → ingresar | La cola local (IndexedDB) se envía **por `POST /contingencia/comandas`**, en orden y de a una; sin duplicados (`X-Command-Id`). Las comandas enviadas a cocina aparecen en **Impresiones retenidas** (la cocina ya las atendió en papel: la caja decide si imprimir); los rechazos van a la bandeja de conflictos, con correo al dueño. En un celular de garzón: «Sin conexión: usa la caja» y no guarda nada |
| S10 | Bloqueo de autorización | Ejecutar `caja/09-retiro-codigo-incorrecto.json` cambiando cada vez el `x-command-id`, hasta sumar 5 intentos fallidos en 15 minutos (el flujo del §2 ya hizo uno) | Cada intento responde `403 CODIGO_AUTORIZACION_INVALIDO` con los intentos restantes (4, 3, 2, 1, 0); el 5.º deja bloqueado al autorizador. Luego `caja/08-retiro.json` (código correcto, con otro `x-command-id`) da `403 AUTORIZACION_BLOQUEADA` por 15 minutos. Correo al dueño. `mock-dueno` (código 1234) sí puede autorizar |
| S11 | Turno abierto demasiado tiempo | `tareas-programadas` con `HORAS_TURNO=0` (versión + alias) y esperar la siguiente ejecución (≤ 5 min) | Un correo al dueño por turno abierto, una sola vez |
| S12 | Reglas de distribución | PWA → Administración → Mensajería: destino «Contabilidad» (cola) con *documento rechazado* y «Caja central» (cola) con *comanda en conflicto* → «Enviar aviso de prueba» *documento rechazado* | Respuesta «Deben recibirlo: Contabilidad». «Ver mensajes» de Contabilidad muestra el aviso; Caja central no recibe nada. Un destino sin avisos o con un correo inválido se rechaza con el mensaje del campo. Sin Google: `probar_nube.py` §3 hace lo mismo |
| S13 | Mensaje fallido, diagnóstico y reproceso | S5 (`DTE_MODO=error5xx`) y una venta; esperar los 5 intentos (unos 20 min) | El documento queda `fallido` y su mensaje aparece en Mensajería → «Mensajes fallidos» con «Proveedor no disponible (error5xx)» e intento 5. Volver a `DTE_MODO=ok` → **Reprocesar** → el documento queda `emitido` con folio. **Descartar** en otro caso lo borra de la cola de fallidos |

## 6. Simulador de impresora (`scripts/simulador_impresora.py`)

Consulta `impresion` exactamente como una impresora CloudPRNT: POST de estado, GET del trabajo y
DELETE de confirmación, con autenticación Basic.
```
$env:POS_CLAVE_IMPRESORA = "mock-clave-cocina"
python scripts/simulador_impresora.py --api <Invoke URL> --impresora imp_cocina
```
- Cada comanda aparece en la terminal y queda en `impresiones/imp_cocina/<trabajo>.txt`.
- `--una-vez`: imprime lo pendiente y termina.
- `--fallar "500 Error"`: informa un error de la impresora. El trabajo sigue pendiente y se reintenta;
  al 5.º error pasa a `HECHO` con estado `error`. Si un trabajo queda pendiente más de 10 minutos,
  `tareas-programadas` avisa a alertas técnicas.
- Para la boleta: `--impresora imp_caja` con `mock-clave-caja`.
- Clave equivocada: termina con «credenciales rechazadas» (401).

## 7. Alarmas de CloudWatch

Todas avisan a `pos-alertas-tecnicas` (configuración exacta en `03` §16):

| Alarma | Umbral | Cómo provocarla a propósito |
|---|---|---|
| Mensajes en cualquier cola de fallidos (3 alarmas) | 1 o más | S5 |
| Antigüedad del mensaje más antiguo en `dte-emision` | > 15 minutos | S5 con `DTE_TASA_FALLA=1` y varias ventas seguidas |
| Antigüedad del mensaje más antiguo en `contingencia-comandas.fifo` | > 5 minutos | Desactivar el disparador del drenador y ejecutar S1 |
| Errores en funciones | > 0 | Un evento de prueba con un `x-command-id` inválido **no** cuenta (es un 422); sirve una función sin una variable de entorno |
| Limitaciones en funciones | > 0 | S2 |
| Respuestas 5xx del API | > 1 % | S2 llamando a la API real |
| Antigüedad del iterador del disparador de Streams | > 60 s | Desactivar el disparador de `procesador-eventos` unos minutos con tráfico, y reactivarlo |

## 8. Definición de terminado

| Criterio | Estado |
|---|---|
| Todas las pruebas locales pasan | ✔ |
| Cada función tiene su carpeta (y su `.zip`) lista para la consola; existe el `.zip` de la capa | ✔ (`dist/`) |
| La guía de consola permite desplegar desde cero sin preguntar | ✔ `03` |
| `validar_despliegue.py` pasa completo contra el despliegue | ✔ simulado · **pendiente contra AWS** (requiere el ID de cliente de Google) |
| Simulacros de documento tributario, contingencia y corte de red sin duplicados ni comandas perdidas | S1–S13 listos para ejecutar |
| Lista explícita de diferencias entre el POS local y la nube | ✔ `caracterizacion.md` |
