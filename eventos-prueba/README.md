# Eventos de prueba

Generado por `scripts/generar_eventos_prueba.py`. No editar a mano.

Requisitos: la herramienta `semilla` ya ejecutada (datos mock). En la consola de Lambda: función → pestaña **Test** → **Create new event** → pega el JSON → **Test**.

Reemplaza `REEMPLAZAR_TURNO_ID` por el `turno_id` que devuelve `caja/01-abrir-turno`, y `REEMPLAZAR_TRABAJO_ID` por el `jobToken` de `impresion/01-consulta-cocina`.

Repetir un evento de escritura devuelve la respuesta guardada (idempotencia). Para ejecutarlo de nuevo de verdad, cambia su `x-command-id` por otro ULID.

| Orden | Función | Evento | HTTP esperado | Qué comprobar |
|---|---|---|---|---|
| 1 | `salon` | `01-salud.json` | 200 | DynamoDB responde |
| 2 | `salon` | `02-yo.json` | 200 | mock-garzon es garzon en MISE Centro |
| 3 | `salon` | `03-plano.json` | 200 | 12 mesas, todas libres |
| 4 | `salon` | `04-catalogo.json` | 200 | 10 productos |
| 5 | `pedidos` | `01-abrir-mesa.json` | 201 | pedido 01K7H0Z3Q8W4M2N5P6R7S8T9W4 en la mesa 5 |
| 6 | `pedidos` | `02-agregar-pizza-xl.json` | 201 | precio congelado 12.900 |
| 7 | `pedidos` | `03-agregar-bebidas.json` | 201 | subtotal 3.600 |
| 8 | `pedidos` | `04-enviar-tanda.json` | 200 | tanda 1; Cocina y Barra: encolada |
| 9 | `pedidos` | `05-ver-pedido.json` | 200 | total 16.500 |
| 10 | `pedidos` | `06-precuenta.json` | 200 | pedido y mesa en precuenta |
| 11 | `pedidos` | `07-reabrir-sin-confirmar.json` | 422 | CONFIRMACION_REQUERIDA (M13) |
| 12 | `salon` | `05-bloquear-mesa.json` | 200 | mesa 12 bloqueada |
| 13 | `impresion` | `01-consulta-cocina.json` | 200 | jobReady: true; copia el jobToken |
| 14 | `impresion` | `02-descargar.json` | 200 | texto de la comanda de cocina |
| 15 | `impresion` | `03-confirmar.json` | 200 | confirmado: true |
| 16 | `caja` | `01-abrir-turno.json` | 201 | copia el turno_id |
| 17 | `caja` | `02-turno-actual.json` | 200 | sin totales (arqueo ciego) |
| 18 | `caja` | `03-pendientes.json` | 200 | la mesa 5 por cobrar |
| 19 | `caja` | `04-pagar.json` | 201 | vuelto 1.850, saldo 0 |
| 20 | `caja` | `05-finalizar-boleta.json` | 200 | documento pendiente; la mesa 5 queda libre |
| 21 | `caja` | `06-documento.json` | 200 | pendiente, y en segundos emitido con folio |
| 22 | `caja` | `07-autorizadores.json` | 200 | mock-dueno y mock-admin |
| 23 | `caja` | `08-retiro.json` | 201 | autorizado por mock-admin |
| 24 | `caja` | `09-retiro-codigo-incorrecto.json` | 403 | CODIGO_AUTORIZACION_INVALIDO, 4 intentos restantes |
| 25 | `caja` | `10-conteo.json` | 200 | conteo_completado: true (50.000 + 18.150 − 5.000) |
| 26 | `caja` | `11-conciliacion.json` | 200 | conciliación registrada |
| 27 | `caja` | `12-cerrar-turno.json` | 200 | diferencia_efectivo: 0 |
| 28 | `reportes` | `01-turnos.json` | 200 | el turno cerrado |
| 29 | `reportes` | `02-turno.json` | 200 | caja y, en segundos, resumen con 1 venta |
| 30 | `administracion` | `01-listar-productos.json` | 200 | 10 productos |
| 31 | `administracion` | `02-crear-sector.json` | 201 | sector nuevo |
| 32 | `administracion` | `03-sector-duplicado.json` | 409 | DUPLICADO |
| 33 | `administracion` | `04-listar-personal.json` | 200 | 6 personas mock |
| 34 | `administracion` | `05-ver-configuracion.json` | 200 | umbral 2 %, mínimo 5.000 |
| 35 | `contingencia` | `01-comanda.json` | 202 | aceptada_en_contingencia (queda en la cola FIFO) |
| 36 | `drenador-contingencia` | `01-abrir-mesa-m07.json` | — | batchItemFailures: []; la mesa 7 queda ocupada con origen "contingencia" |
| 37 | `drenador-contingencia` | `02-agregar-a-mesa-ya-cobrada.json` | — | batchItemFailures: [] (no se reintenta); queda un CONFLICTO# y llega un correo al dueño |
| 38 | `caja` | `13-conflictos.json` | 200 | un conflicto PEDIDO_CERRADO de la mesa 5 |
| 39 | `emision-dte` | `01-mensaje.json` | — | batchItemFailures: [] (si ya estaba emitido, no hace nada) |
| 40 | `procesador-eventos` | `01-registro-no-evento.json` | — | batchItemFailures: [] (lo descarta: no es un evento) |
| 41 | `tareas-programadas` | `01-regla-eventbridge.json` | — | conteos de lo reencolado y avisado |
| 42 | `reservas` | `01-disponibilidad.json` | 501 | NO_IMPLEMENTADO (esqueleto) |
| 43 | `pedidos-externos` | `01-webhook-firma-invalida.json` | 401 | FIRMA_INVALIDA |
