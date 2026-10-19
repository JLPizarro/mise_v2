# MISE POS — PWA v2

PWA React que habla **directo** con el API Gateway (sin servidor en el local). Plan, decisiones y
contrato con las Lambdas: [`docs/migracion/07-plan-pwa.md`](../docs/migracion/07-plan-pwa.md).

## Desarrollo

1. `copy config.example.json public\config.json`
2. En otra terminal, desde `POS/POS`: `python scripts\servidor_local.py`
   (emula el API Gateway con las Lambdas reales y datos simulados en memoria; necesita
   `requirements-dev.txt`). Con él no hace falta AWS ni el ID de cliente de Google.
3. `npm run dev`
4. Abrir `http://localhost:8000` y entrar con un botón «Entrar como mock-…».

Para probar la contingencia: `curl -X POST http://localhost:8001/__dev/fallas -d "{\"rutas_normales\": true}"`
(y `false` para quitarla).

## Comandos

| Comando | Qué hace |
|---|---|
| `npm run lint` | ESLint |
| `npm run test` | Pruebas unitarias (vitest) |
| `npm run build` | Tipos + compilación en `dist/`, con `precache.json` y el service worker versionado |
| `npm run preview` | Sirve `dist/` en `http://localhost:8000` (el service worker solo funciona aquí, no en `dev`) |

## Publicación

`dist/` se publica en el bucket `pos-sitio-<cuenta>` con `infra/cloudshell/publicar_pwa.sh` (ver
`docs/migracion/06-despliegue-cloudshell.md`, paso 9). La dirección del API y el ID de cliente de
Google **no** están en el código: van en `config.json`, que escribe ese script.

## Reglas que no se rompen

- El token de Google vive solo en memoria: nunca en `localStorage`, IndexedDB ni logs.
- Montos en pesos enteros; nunca `parseFloat` para dinero.
- Cada intención del usuario crea un solo comando con `X-Command-Id`; los reintentos, la contingencia y
  la cola local reutilizan el mismo ID y el mismo cuerpo.
- IndexedDB (`pos-caja`) solo en un equipo registrado como estación de caja.
