# Caracterización y diferencias entre el POS local y la nube

Regla de la migración: **no cambiar resultados sin reportarlo**. Este documento lista qué
comportamiento del POS local quedó fijado en pruebas y cada diferencia de la versión en la nube, con
la prueba que la documenta. Se actualiza en cada fase.

## Cómo se caracterizó

| Origen | Cómo se ejecuta | Pruebas |
|---|---|---|
| Backend (FastAPI) | Copia congelada de los casos de uso en `tests/caracterizacion/legado/` (sin modificar), ejecutada con repositorios en memoria que reproducen el SQL de Postgres (`dobles.py`, cada método cita su sentencia) | `test_legado_pedidos.py`, `test_legado_pagos_caja.py` (67 pruebas) |
| Frontend (React) | Transcripción literal de las funciones de `PendientesCaja.tsx`, `FormularioPago.tsx` y `pagos.service.ts` en `reglas_caja.mjs`, ejecutada con Node para producir `golden.json` | `tests/dominio/test_dinero_vs_frontend.py` compara el dominio nuevo contra `golden.json` y verifica que el golden siga coincidiendo con la transcripción |
| Umbral del arqueo | Se llama directamente a `calcular_umbral_diferencia` de la copia congelada | `test_umbral_vs_legado.py`: idéntico en más de 900.000 combinaciones, incluso con porcentajes como 3,33 % |

Límite conocido: los dobles en memoria reproducen el SQL según su lectura; no ejecutan Postgres. Las
funciones del frontend están dentro de componentes y no se pueden importar, así que se transcribieron.

## Comportamientos que se conservan

| Regla | Local | Nube | Prueba |
|---|---|---|---|
| Comanda por tandas: enviar manda todos los ítems en espera; los ya enviados no cambian | ✔ | ✔ | `TestTandasYEspera`, `test_tandas_envian_solo_lo_que_espera...` |
| Ítems nuevos nacen en espera; solo se quitan mientras esperan | ✔ | ✔ | ídem |
| Enviar sin ítems en espera no es error y no escribe | ✔ | ✔ | `test_enviar_sin_items_en_espera_no_escribe` |
| Precio congelado = precio + recargo del modificador al agregar | ✔ | ✔ | `test_precio_congelado...` |
| Abrir una mesa con pedido devuelve el mismo pedido; se conserva el garzón ya asignado | ✔ | ✔ | `TestAbrir` |
| Partes iguales: base = saldo ÷ n, el resto de a $1 en las primeras partes, 2 a 20 personas | ✔ | ✔ | `test_partes_iguales` |
| Por ítems: monto = mín(Σ precio congelado × cantidad, saldo) | ✔ | ✔ | `test_monto_por_items` |
| Monto libre: entre 1 y el saldo | ✔ | ✔ | golden `monto_libre` |
| Propina sugerida = redondeo hacia arriba en la mitad de monto × % ÷ 100 sobre lo que se cobra en ese paso | ✔ | ✔ | `test_propina_sugerida...` (200.001 montos × 4 %) |
| Pago mixto: hasta 2 medios; el último cubre el resto; toda la propina va al último | ✔ | ✔ | `test_en_pago_mixto_el_ultimo_medio_cubre_el_resto` |
| Tarjeta exige código del terminal; efectivo recibido ≥ monto + propina | ✔ (en la pantalla) | ✔ (en el servidor) | `test_validaciones_de_medio` |
| La propina no consume saldo | ✔ | ✔ | `test_pagos_mixtos...`, `test_pago_mixto_es_un_solo_comando...` |
| Esperado = apertura + Σ(monto + propina) en efectivo − retiros | ✔ | ✔ | `TestArqueoCiego`, `TestTurnoYArqueo` |
| Umbral = máx(round(esperado × % ÷ 100), mínimo), con redondeo al par; recuento si la diferencia lo **supera** (estricto) | ✔ | ✔ | `TestUmbral`, `test_umbral_vs_legado.py` |
| El recuento se acepta aunque siga fuera y es definitivo | ✔ | ✔ | `test_el_recuento_se_acepta...` |
| Cierre: exige conteo, recuento si correspondía y conciliación; totales por medio incluyen propina | ✔ | ✔ | `test_cierre_exige_pasos_en_orden`, `test_arqueo_ciego_con_recuento...` |
| La conciliación del terminal se puede corregir mientras el turno esté abierto (D17) | ✔ | ✔ | `test_la_conciliacion_se_puede_sobrescribir` |
| Un solo turno de caja abierto por local | ✔ | ✔ | `test_un_solo_turno_abierto` |
| Código de autorización: 4 a 8 dígitos, PBKDF2-SHA256 de 200.000 iteraciones con sal por persona | ✔ | ✔ (iteraciones guardadas junto al hash) | `pos_dominio.autorizacion` |

## Diferencias (cada una intencional)

| # | Local | Nube | Prueba |
|---|---|---|---|
| D1 | Se agregan ítems a pedidos en precuenta o cerrados | 409 `PEDIDO_EN_PRECUENTA` / `PEDIDO_CERRADO` | `test_D1_M13_en_precuenta_no_se_agrega_sin_reabrir` |
| M13 | — | Reabrir la mesa en precuenta exige confirmación explícita del garzón (`confirmado: true`) | `test_M13_reabrir_exige_confirmacion_del_garzon` |
| D2 | Precuenta reabre un pedido cerrado; se permite con el pedido vacío | Solo desde `abierto` y con consumo (`PEDIDO_VACIO`) | `test_precuenta_de_pedido_vacio_se_rechaza` |
| D3 | Un ítem enviado se puede achicar, volver a espera y borrar | 409 `ITEM_YA_ENVIADO`; el estado del ítem solo cambia al enviar la tanda | `test_D3_un_item_enviado_no_se_modifica_ni_se_quita` |
| D5 | Mesa bloqueada recibe pedido; dos garzones pueden abrir dos pedidos en la misma mesa | 409 `MESA_BLOQUEADA`; la segunda apertura recibe el pedido de la primera | `test_D5_...` (dos pruebas) |
| D6 | Dos cobros simultáneos pueden superar el total | El segundo relee y recibe `MONTO_EXCEDE_SALDO` | `test_D6_dos_cobros_simultaneos_no_superan_el_total` |
| D7 | Pago sin pedido no valida saldo | `pedido_id` es obligatorio | `leer_pago` |
| D8 | Efectivo recibido, vuelto, tipo de documento y receptor nunca llegan al servidor | Llegan; el vuelto lo calcula el servidor; el documento se informa al finalizar | `test_pago_mixto_es_un_solo_comando...`, `TestFinalizar` |
| D9 | Pago mixto = un POST por medio, sin atomicidad | Un solo comando con 1 o 2 medios | ídem |
| D12 | Código inválido = 401 y el frontend cierra la sesión del cajero | 403 `CODIGO_AUTORIZACION_INVALIDO`, con intentos restantes | `test_D12_codigo_invalido_es_403...` |
| D13 | El código se prueba contra todos los admins; gana el primero que calce | Se elige al autorizador; un solo cálculo; bloqueo de 5 intentos en 15 min por autorizador | `TestRetiros` |
| D22 | Partes de $0 si hay más personas que pesos | 422 `PARTE_EN_CERO` | `test_partes_iguales` |
| D23 | Un ítem repetido en la selección permite cobrar más unidades de las que existen | Se suman antes de validar | `test_monto_por_items`, `test_division_por_items_valida_monto_y_unidades` |
| D24 | La vista previa por ítems mostraba el precio actual del catálogo | Siempre el precio congelado | `test_D24_...` |
| — | Por ítems, el servidor aceptaba cualquier monto | El monto debe coincidir con los ítems (`MONTO_NO_CORRESPONDE`) | `test_division_por_items_valida_monto_y_unidades` |
| — | `items_cobrados` se aceptaba con cualquier tipo de división | Solo con `tipo_division = items` | `decidir_pago` |
| — | Propina sin validación (la base la rechazaba con error 500) | `propina ≥ 0` → 422 | `test_validaciones_de_medio` |
| — | Finalizar no exigía turno | Exige turno abierto (la venta se asocia a él) | `test_finalizar_exige_turno_abierto` |
| M14 | Cerrar una mesa sin consumo cerraba "la venta" de $0 | Se libera sin documento (`pedido.cerrado_sin_venta`) | `test_M14_mesa_sin_consumo...` |
| — | Finalizar dos veces volvía a cerrar | Idempotente por estado: devuelve el pedido cerrado sin escribir | `test_finalizar_dos_veces...` |
| — | `cocina` podía escribir comandas y cambiar mesas | Sin permisos de escritura | `test_cocina_no_puede_abrir_mesas` |
| — | Cantidad sin tope; observación sin largo máximo | Cantidad 1–999; observación ≤ 500; ≤ 300 líneas por pedido; ≤ 80 por tanda | `test_validaciones_al_agregar` |
| — | Ítem enviado o inexistente al quitar: ambos 404 | Inexistente 404, enviado 409 | `test_D3_...` |
| — | Conteo con el turno abierto devolvía el turno con todos sus campos | Mientras está abierto, la vista del turno no expone totales (arqueo ciego también por la API) | `test_arqueo_ciego_con_recuento...` |
| — | Errores de validación de negocio = 400 | 422 (validación) o 409 (estado), formato `{codigo, mensaje, requestId}` | todas |
| — | `POST /api/pedidos` respondía 201 también al devolver uno existente | 201 al crear, 200 al devolver el existente | `test_segunda_apertura...` |
| — | Respuesta de enviar tanda = lista de ítems | `{tanda, items, impresion}` | `test_tandas_envian...` |
| — | Cierre de turno | Agrega `total_transferencia_mise`, `total_retiros`, `umbral`, `fuera_de_umbral`, `n_ventas`, `total_ventas` | `test_arqueo_ciego_con_recuento...` |

## Diferencias agregadas en la Fase 3 (funciones)

| # | Local | Nube | Prueba |
|---|---|---|---|
| D4 | `PATCH /api/mesas/{id}` dejaba a cualquier rol cambiar cualquier campo | Estructura solo D/A (administración); bloquear y asignar garzón D/A/C; no se bloquea una mesa con pedido | `test_garzon_no_bloquea_mesas`, `test_cajero_bloquea_y_la_mesa_no_recibe_pedidos` |
| D10 | El botón de propina sugerida usaba 10 % fijo | La PWA recibe `propina_sugerida_pct` del local en `GET /yo` | `GET /yo` |
| D14 | Editar modificadores de un producto vendido daba 500 | ID estable por modificador | `test_producto_con_modificadores_estables` |
| D15 | Sector, cuarto o mesa duplicados daban 500 | 409 `DUPLICADO` (nombres comparados sin mayúsculas ni espacios extra) | `test_crear_sector_y_mesa_duplicada_es_409` |
| D16 | Un admin podía crear dueños o ascenderse | Solo un dueño otorga o modifica el rol dueño; nadie cambia su propio rol | `test_admin_no_puede_crear_duenos`, `test_nadie_cambia_su_propio_rol` |
| D19 | `/api/health` no revisaba la base | `/salud` lee DynamoDB y responde 503 si falla | `test_salud_responde_503_si_dynamodb_falla` |
| D21 | Login legado que creaba cuentas con cualquier email | Eliminado: el alta es por invitación y el primer ingreso la vincula | `test_invitacion_se_vincula_en_el_primer_ingreso` |
| — | Borrar personal con historial lo desactivaba; sin historial lo borraba | Siempre se archiva (pierde el acceso en ≤ 60 s) | `test_archivar_quita_el_acceso` |
| — | Impresora = IP y puerto (nunca se usó) | Impresora con protocolo CloudPRNT y clave propia (Basic), rotable | `TestImpresion` |
| — | Cuarto con impresora embebida | El cuarto apunta a una impresora (`impresora_id`) | ídem |
| — | Stock y cantidades de receta como decimal | Se guardan en milésimas enteras; la API sigue aceptando hasta 3 decimales | `decidir_crear_materia_prima` |
| — | Umbral de diferencia como decimal | Puntos base enteros; la API sigue aceptando hasta 2 decimales | `test_umbral_en_porcentaje_se_guarda_en_puntos_base` |
| — | La caja armaba la lista de cobro con N peticiones | `GET /caja/pendientes` en una sola | `test_pendientes_pago_y_finalizar` |
| — | Sin refresco del plano | `GET /salon?solo_estado=1` liviano para refrescar; la carta solo se reenvía si cambió su versión | `test_catalogo_sin_cambios_no_reenvia_productos` |
| — | — | El cliente puede proponer el ULID del pedido y del ítem nuevos (necesario para seguir trabajando en contingencia) | `test_reaplica_en_orden_con_ids_del_cliente...` |

D20 (refresco del plano en pantalla) y el resto de la experiencia en la PWA se resuelven en la fase
del frontend.
