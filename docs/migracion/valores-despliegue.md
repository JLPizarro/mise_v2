# Valores del despliegue

Plantilla para anotar lo que se crea en la consola (`03-guia-consola.md`). No contiene secretos: no
anotes aquí claves de impresora reales, códigos de autorización ni tokens.

| Dato | Valor |
|---|---|
| ID de cuenta (`<cuenta>`) | |
| Cuota de concurrencia de Lambda | |
| Bucket del sitio | `pos-sitio-<cuenta>` |
| URL del sitio | `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/` |
| Bucket del archivo | `pos-archivo-<cuenta>` |
| URL cola `dte-emision` | |
| URL cola `contingencia-comandas.fifo` | |
| ARN cola `procesador-eventos-fallidos` | |
| ARN tema `pos-avisos-dueno` | |
| ARN tema `pos-alertas-tecnicas` | |
| Versión de la capa `pos-dominio` en uso | |
| Invoke URL de `pos-api` (stage `prod`) | |
| ID de cliente OAuth de Google | **PENDIENTE** |
| Emisor real del ID token (`iss`) | |

## Versiones publicadas por función (alias `vivo`)

| Función | Versión en `vivo` | Versión anterior (para revertir) | Fecha |
|---|---|---|---|
| salon | | | |
| pedidos | | | |
| caja | | | |
| administracion | | | |
| reportes | | | |
| impresion | | | |
| contingencia | | | |
| reservas | | | |
| pedidos-externos | | | |
| procesador-eventos | | | |
| emision-dte | | | |
| drenador-contingencia | | | |
| tareas-programadas | | | |
