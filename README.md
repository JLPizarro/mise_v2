# MISE POS v2 — serverless en AWS

Punto de venta para restaurantes, sin servidor en el local. Garzones y caja usan una PWA que habla
directo con un API Gateway en AWS. Las tareas que pueden esperar (documento tributario, avisos,
archivo histórico, comandas en contingencia) viajan por mensajería asíncrona.

| Carpeta | Contenido |
|---|---|
| `pwa/` | **Frontend**: PWA en React con inicio de sesión de Google, cola local de la estación de caja y administración (incluida Mensajería) |
| `lambdas/funciones/` | **Backend**: 14 funciones Lambda, una carpeta por servicio (`salon`, `pedidos`, `caja`, `administracion`, `reportes`, `impresion`, `contingencia`, `reservas`, `pedidos-externos`, `mensajeria`, `procesador-eventos`, `emision-dte`, `drenador-contingencia`, `tareas-programadas`) |
| `lambdas/capa/python/pos_dominio/` | Capa compartida: reglas de negocio, catálogo de mensajería (`mensajeria.py`) y adaptadores de AWS (`infra/`) |
| `infra/` | Despliegue con un script desde CloudShell (`infra/cloudshell/desplegar.sh`) y tabla de Athena |
| `scripts/` | Empaquetado, servidor local de desarrollo, validación y prueba en la nube |
| `tests/` | Pruebas del dominio, de las funciones (con AWS simulado) y de los scripts |
| `docs/migracion/` | Documentación: arquitectura, modelo de datos, API, despliegue, riesgos, validación y mensajería (`08-mensajeria.md`) |

La versión 1 (nodo local con FastAPI, SQLite y frontend propio) quedó en el repositorio anterior y está
deprecada. `docs/migracion/00-inventario.md` y `caracterizacion.md` documentan cómo era y qué cambió.

## Probar en tu PC

```
python -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
cd pwa && npm ci && npm run test && npm run build
```

Para desarrollar la PWA sin AWS ni Google, levanta `python scripts/servidor_local.py` y sigue
`pwa/README.md`.

## Desplegar

Sigue `docs/migracion/06-despliegue-cloudshell.md`. Necesitas el Learner Lab de AWS Academy
(us-east-1, rol LabRole) y un ID de cliente OAuth de Google para iniciar sesión. El repositorio no
guarda secretos: el ID de cliente y los valores de la cuenta se escriben en archivos ignorados por git.
