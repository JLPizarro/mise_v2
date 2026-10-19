# Costo estimado en AWS

Estimación sobre papel, no medida. Precios de `us-east-1` conocidos a octubre de 2026, sin capa
gratuita (en el Learner Lab no es seguro que aplique). Confirmar en la calculadora de AWS.

## Supuestos: restaurante grande, día lleno

| Supuesto | Valor |
|---|---|
| Mesas / garzones / cajas | 40 / 15 / 2 |
| Horario | 12 h (almuerzo y cena) |
| Ventas al día | 200 (~600 cubiertos) |
| Por venta | 8 líneas, 3 tandas, 1,3 pagos, precuenta y cierre (≈ 16 escrituras) |
| Plano de mesas | 18 equipos refrescando cada 10 s |
| Pantalla de caja | refresca pendientes cada 10 s |
| Impresoras | 3 de cocina + 1 de caja, consultando cada 5 s durante 14 h |

## Peticiones al día

| Origen | Peticiones/día | % |
|---|---|---|
| Refresco del plano | 77.800 | 58 % |
| Consulta de impresoras | 42.500 | 32 % |
| Refresco de la caja | 8.600 | 6 % |
| Ventas (comanda, pagos, cierre) | 4.300 | 3 % |
| Total | ≈ 134.000 | |

## Costo mensual por local

| Servicio | Mes lleno (30 días) | Mes típico (8 llenos + 22 normales) |
|---|---|---|
| API Gateway (USD 1 por millón) | USD 4,0 | USD 3,2 |
| DynamoDB escrituras (~300 unidades por venta) | USD 1,1 | USD 0,6 |
| DynamoDB lecturas | USD 1,1 | USD 0,9 |
| Lambda (peticiones + tiempo, arm64) | USD 1,6 | USD 1,3 |
| CloudWatch Logs (~3 GB) | USD 1,5 | USD 1,2 |
| S3 (archivo por evento + comprobantes) | USD 0,6 | USD 0,3 |
| SQS (consulta de colas vacías por las funciones) | USD 0,6 | USD 0,6 |
| Alarmas (~9) | USD 0,9 | USD 0,9 |
| SNS, EventBridge, Athena, almacenamiento | < USD 0,1 | < USD 0,1 |
| **Total** | **≈ USD 11–12** | **≈ USD 9** |

- Por venta: ≈ USD 0,002.
- Alarmas y consulta de colas (~USD 1,5) son fijos de la plataforma, no de cada local.
- Transferencia (~10 GB/mes por local) dentro de los 100 GB mensuales gratuitos de AWS.

## El cierre de caja es O(1)

Cada pago y retiro suma a los totales del turno en su misma transacción (M5). Cerrar el turno lee y
escribe un solo ítem, sin importar cuántas ventas hubo. El reporte del turno con 200 ventas lee unos
400 KB (≈ 100 unidades de lectura, USD 0,00001).

## Palancas de costo

1. Refresco del plano y la caja: de 10 s a 30 s, y pausado con la pantalla oculta → la mitad o menos.
2. Intervalo de consulta de las impresoras (CloudPRNT): de 5 s a 10 s → −15 % del total.
3. Retención de los logs de cada función en 7 días (si queda "nunca expira" se acumulan).
4. Arranques en frío: AWS los cobra desde 2025; ~USD 0,1 al mes con este tráfico.

Con 1 y 2, el mes lleno baja a ~USD 6 por local.
