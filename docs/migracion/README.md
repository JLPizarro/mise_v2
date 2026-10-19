# Migración del POS a AWS Lambda

## Para llegar y probar

1. En tu computador, desde `POS/POS`:
   ```
   py -3.13 -m venv .venv
   .venv\Scripts\pip install -r requirements-dev.txt
   .venv\Scripts\python -m pytest -o addopts=""                    # todas las pruebas locales
   .venv\Scripts\python scripts/validar_despliegue.py --simulado   # el sistema completo en memoria
   .venv\Scripts\python scripts/construir_capa.py                  # .zip para la consola (dist/)
   ```
2. En el Learner Lab: [`03-guia-consola.md`](03-guia-consola.md), pasos 0 a 16, anotando cada valor
   en [`valores-despliegue.md`](valores-despliegue.md).
3. Probar sin Google: [`../../eventos-prueba/README.md`](../../eventos-prueba/README.md) en orden, y el
   simulador de impresora.
4. Cuando exista el ID de cliente de Google (**pendiente**): `03` §17 y `validar_despliegue.py` contra AWS.
5. Simulacros: [`05-validacion.md`](05-validacion.md) §5.

**Camino rápido:** [`06-despliegue-cloudshell.md`](06-despliegue-cloudshell.md) hace los pasos 2 a 5 con dos scripts desde CloudShell (unos 30 minutos).

## Documentos

| Documento | Contenido |
|---|---|
| [`arquitectura.html`](arquitectura.html) | Diagramas de los flujos (ábrelo en el navegador) |
| [`00-inventario.md`](00-inventario.md) | El POS local tal como estaba, defectos encontrados y decisiones del equipo |
| [`01-modelo-dynamodb.md`](01-modelo-dynamodb.md) | Claves de las dos tablas, patrones de acceso y qué escribe cada transacción |
| [`02-api-gateway.md`](02-api-gateway.md) | Las 59 rutas, autorizador, CORS, límites, y la configuración de cada función, disparador y cola |
| [`03-guia-consola.md`](03-guia-consola.md) | Despliegue paso a paso desde la consola |
| [`04-riesgos-y-reversion.md`](04-riesgos-y-reversion.md) | Cada falla posible, cómo detectarla y resolverla; cómo revertir |
| [`05-validacion.md`](05-validacion.md) | Pruebas, datos mock, validación de punta a punta, simulacros y alarmas |
| [`06-despliegue-cloudshell.md`](06-despliegue-cloudshell.md) | Despliegue y prueba con scripts desde CloudShell |
| [`07-plan-pwa.md`](07-plan-pwa.md) | PWA v2 (carpeta `pwa/`): decisiones, contrato con las Lambdas, código base y fases. Ya ejecutado; se publica con `publicar_pwa.sh` (ver `06` §9) |
| [`08-mensajeria.md`](08-mensajeria.md) | Mensajería asíncrona: catálogo de canales y rutas, destinos y reglas, consumidores, reintentos, mensajes fallidos y su administración |
| [`caracterizacion.md`](caracterizacion.md) | Qué se conserva del POS local y la lista explícita de diferencias |
| [`costos.md`](costos.md) | Costo estimado por local |
| [`valores-despliegue.md`](valores-despliegue.md) | Plantilla para anotar ARN, URL y versiones |

## Pendientes conocidos

- **ID de cliente OAuth de Google**: el autorizador queda con audiencia `PENDIENTE` (rutas privadas en 401) y la PWA no puede iniciar sesión en la nube hasta tenerlo (con el servidor local sí: `pwa/README.md`).
- **Reservas y pedidos externos**: esqueletos con su seguridad; faltan sus reglas de negocio.
- CloudFront no está disponible en este entorno y no se usa: el sitio se sirve desde S3 por HTTPS.
