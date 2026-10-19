# 06 — Despliegue y prueba desde CloudShell

Camino rápido para dejar todo arriba en una sesión del Learner Lab: un script crea toda la
infraestructura y otro la prueba. Toma unos 30 minutos en total.

> Esto usa la AWS CLI (dentro de CloudShell), a diferencia de la decisión inicial de configurar todo
> solo desde la consola. Si la evaluación exige consola, `03-guia-consola.md` sigue siendo el camino
> válido y deja exactamente lo mismo. El script no pide credenciales: CloudShell usa la sesión del
> laboratorio.

**Pendiente: el ID de cliente OAuth de Google.** Sin él todo funciona y se prueba con datos mock; el
autorizador queda con audiencia `PENDIENTE` (rutas privadas en 401). El paso 8 lo completa.

---

## 1. En tu computador (2 minutos)

Desde `POS/POS`, en la rama `feature/migracion-lambdas`:
```
python scripts/paquete_cloudshell.py
```
Queda `dist/pos-cloudshell.zip`, con el código, los scripts, los eventos de prueba, la tabla de rutas
y, si existe, la PWA compilada (`pwa/dist`; ver el paso 9). Los finales de línea se convierten al
formato de Linux (salvo en `pwa/dist`, que no se toca).

## 2. Abrir CloudShell (2 minutos)

1. Learner Lab → **Start Lab** → espera el círculo verde → **AWS**.
2. Región arriba a la derecha: **N. Virginia (us-east-1)**.
3. Ícono de **CloudShell** en la barra superior (`>_`). Espera a que aparezca el prompt.
4. **Actions → Upload file** → `dist/pos-cloudshell.zip`.
5. En CloudShell:
   ```
   unzip -o pos-cloudshell.zip -d pos && cd pos
   ```

**Si CloudShell no deja subir el .zip:** el paso 1 también deja `dist/cloudshell-partes/pos-parte-01.txt`,
`pos-parte-02.txt`, …: el mismo paquete en texto (base64), partido en archivos de unos 60 KB (hasta
99 partes; el número lleva dos dígitos para que `cat pos-parte-*.txt` las ordene bien).
1. **Actions → Upload file** con cada parte, una por una. Quedan en la carpeta de inicio (`~`).
2. Rearma y comprueba:
   ```
   cd ~ && ls pos-parte-*.txt
   cat pos-parte-*.txt | base64 -d > pos-cloudshell.zip && sha256sum pos-cloudshell.zip
   ```
   El código debe ser igual al que mostró el paso 1 en tu computador (`debe mostrar ...`). Si no
   coincide, falta una parte o una quedó a medias: súbela de nuevo.
3. `unzip -o pos-cloudshell.zip -d pos && cd pos` y sigue con el paso 3.

Otra opción, sin CloudShell para la subida: en la consola de S3, crea un bucket cualquiera (por ejemplo
`pos-subida-<tus iniciales>`) y sube ahí el .zip con **Upload**. Luego, en CloudShell:
`aws s3 cp s3://<ese bucket>/pos-cloudshell.zip . && unzip -o pos-cloudshell.zip -d pos && cd pos`.

## 3. Desplegar (10 a 15 minutos)

Opcional, antes de ejecutar:
```
export EMAIL_AVISOS=tu-correo@ejemplo.cl         # recibe los avisos del dueño y las alarmas
export EMAIL_DUENO_REAL=cuenta-google@gmail.com  # queda invitado como dueño (para cuando exista Google)
```
Luego:
```
bash infra/cloudshell/desplegar.sh 2>&1 | tee despliegue.log
```

El script recorre los mismos pasos de la guía 03 y muestra `✔` en cada uno:
1. cuota de Lambda;
2. buckets;
3. tablas con Streams y TTL;
4. colas;
5. temas;
6. logs con retención de 7 días;
7. capa;
8. las 14 funciones con alias `vivo`;
9. disparadores;
10. regla de EventBridge;
11. datos mock, cargados con la semilla temporal que luego se borra;
12. API con 59 rutas;
13. Athena;
14. 9 alarmas.

Al final muestra la **URL del API** (termina en `/prod`) y deja todos los valores en
`valores-despliegue.env`.

- **Si la sesión se corta o algo falla**, vuelve a ejecutar el mismo comando: es idempotente. Lo que
  ya existe se actualiza y no se duplica.
- **Las líneas con `!` son avisos, no errores.** Indican algo que el laboratorio no permitió y la
  alternativa que se aplicó (por ejemplo, el destino ante fallo de Streams, riesgo L1 de 04). Anótalas.
- **Si el script se detiene con un error**, el mensaje de la AWS CLI dice qué faltó. Busca el síntoma
  en `04-riesgos-y-reversion.md`.

Si pusiste `EMAIL_AVISOS`: abre ese correo y pulsa **Confirm subscription** en los dos mensajes de AWS.

## 4. Probar el despliegue (3 a 5 minutos)

```
python3 scripts/probar_nube.py
```
Comprueba, contra la nube real y sin Google:
1. Los **43 eventos** del flujo de la consola, uno por uno (`✔` con su código HTTP): comanda, cocina,
   cobro, cierre de turno, administración, contingencia y conflicto.
2. Lo **asíncrono real**: el documento tributario pasa a `emitido` (Streams → procesador → SQS →
   emisión) y el reporte del turno muestra la venta.
3. El **archivo histórico** en S3.
4. La **API pública**: `/salud` = 200, `/yo` sin token = 401, y la impresora de caja retira e imprime
   la boleta por CloudPRNT (la boleta aparece en la terminal).

Resultado esperado: `TODO EN ORDEN`. Se puede ejecutar varias veces: usa IDs nuevos en cada pasada.

## 5. Mirarlo con tus propios ojos (5 minutos)

| Dónde | Qué ver |
|---|---|
| Navegador: `<URL del API>/salud` | `{"estado":"ok","dynamodb":"ok",...}` |
| Navegador: `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/obtener_token.html` | La página abre por HTTPS |
| DynamoDB → `operacion` → Explore items | Pedidos (`…#PED#…`), eventos (`…#EVT`), turnos, documentos |
| S3 → `pos-archivo-<cuenta>` | `eventos/tenant=demo/fecha=…/` y `comprobantes/…/*.html` (ábrelo) |
| Athena → Query editor | `SELECT tipo, count(*) FROM pos.eventos WHERE tenant='demo' AND fecha = current_date GROUP BY tipo;` |
| CloudWatch → Alarms | Las 9 en **OK** o **Insufficient data** (normal sin tráfico) |
| Lambda → cualquier función → Aliases | `vivo` apuntando a la versión publicada |

Impresora simulada contra la API, en CloudShell:
```
source valores-despliegue.env
POS_CLAVE_IMPRESORA=mock-clave-cocina python3 scripts/simulador_impresora.py --api "$URL_API" --impresora imp_cocina
```
Deja ese comando corriendo y, en otra pestaña de CloudShell (**+**), ejecuta de nuevo
`python3 scripts/probar_nube.py`: las comandas aparecen en la impresora simulada. **Ctrl+C** para
salir.

## 6. Simulacros (opcional hoy, 15 minutos)

`infra/cloudshell/simulacro.sh` cambia una variable, publica una versión y mueve el alias. Al
terminar imprime el comando exacto para volver atrás. Resultados esperados en `05-validacion.md` §5.

```
# S1 · falla de DynamoDB en pedidos: la comanda responde 202 y la aplica el drenador
bash infra/cloudshell/simulacro.sh pedidos SIMULAR_FALLA_DYNAMODB=true
python3 scripts/probar_nube.py          # las escrituras de pedidos responden 202 en vez de 201
bash infra/cloudshell/simulacro.sh pedidos SIMULAR_FALLA_DYNAMODB=

# S5 · proveedor de documentos caído: el cobro no se bloquea; el documento reintenta y termina fallido
bash infra/cloudshell/simulacro.sh emision-dte DTE_MODO=error5xx
# S6 · rechazo de negocio: el documento queda rechazado sin reintentos y llega un correo al dueño
bash infra/cloudshell/simulacro.sh emision-dte DTE_MODO=rechazo
# Vuelta a la normalidad
bash infra/cloudshell/simulacro.sh emision-dte DTE_MODO=ok
```
Durante S1 y S5, `probar_nube.py` muestra `✘` en los pasos afectados: es lo esperado, porque el
simulacro rompe eso a propósito.

## 7. Revertir una función

```
bash infra/cloudshell/revertir.sh pedidos        # muestra versiones y cuál está en vivo
bash infra/cloudshell/revertir.sh pedidos 1      # vuelve vivo a la versión 1
```
Efecto inmediato: la API y los disparadores apuntan al alias.

## 8. Cuando exista el ID de cliente de Google (pendiente)

1. Google Cloud Console:
   - **OAuth consent screen**: External, modo *Testing*, con los correos del equipo como *Test users*.
   - **Credentials → OAuth client ID → Web application**, con *Authorized JavaScript origins*:
     `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com` y `http://localhost:8000`.
2. En CloudShell:
   ```
   bash infra/cloudshell/configurar_google.sh <ID>.apps.googleusercontent.com
   ```
   Si el paquete trae la PWA, este paso también la publica con el ID (paso 9).
3. Abre `obtener_token.html`, pega el ID de cliente e inicia sesión con el email de `EMAIL_DUENO_REAL`.
   Si la página muestra un emisor distinto de `https://accounts.google.com`, ejecuta de nuevo el paso 2
   con ese emisor como segundo argumento.
4. Copia el token y valida de punta a punta. En CloudShell el token es largo: pégalo en un archivo con
   `nano token.txt` y léelo desde ahí.
   ```
   source valores-despliegue.env
   POS_ID_TOKEN="$(cat token.txt)" POS_CLAVE_IMPRESORA=mock-clave-cocina \
     python3 scripts/validar_despliegue.py --api "$URL_API"
   ```
   Resultado esperado: `VALIDACIÓN COMPLETA: N/N pasos` (todos bien, incluida la verificación del token).

## 9. Publicar la PWA

La PWA (`pwa/`) es una aplicación React que habla directo con el API Gateway; se sirve desde el mismo
bucket del sitio (`pos-sitio-<cuenta>`). Se compila en tu computador y se publica desde CloudShell.

1. En tu computador, desde `POS/POS`:
   ```
   cd pwa && npm ci && npm run build && cd ..
   python scripts/paquete_cloudshell.py
   ```
   La compilación deja `pwa/dist` (con `precache.json` y el service worker versionado) y el paquete
   lo incluye. Sube el paquete a CloudShell como en el paso 2 (o sus partes `pos-parte-01.txt`…).
2. En CloudShell, `desplegar.sh` publica la PWA sola si el paquete la trae (paso «15. PWA»). También
   puede hacerse aparte, sin volver a desplegar nada:
   ```
   bash infra/cloudshell/publicar_pwa.sh
   ```
   El script escribe el `config.json` de la nube (`api_url`, `google_client_id`, `modo_dev: false`) en
   un directorio temporal, nunca dentro de `pwa/dist`, y sube en este orden: `assets/` (inmutables),
   el resto de lo estático, manifiesto, service worker, `precache.json` y `config.json` (todos con
   `no-cache`) y, al final, `index.html`. No borra nada: los assets anteriores siguen disponibles.
3. El ID de cliente de Google sale de `GOOGLE_CLIENT_ID` o de `google-client-id.txt`, que deja
   `configurar_google.sh` (paso 8). Ese script, además, vuelve a publicar la PWA con el ID.
4. Abre `https://pos-sitio-<cuenta>.s3.us-east-1.amazonaws.com/index.html` (la dirección exacta sale
   en la línea `PWA:` del resumen de `desplegar.sh` y de `publicar_pwa.sh`). Ingresa con el email de
   `EMAIL_DUENO_REAL`. Para probar sin Google, usa el servidor local (`pwa/README.md`).
5. Una versión nueva se publica volviendo a ejecutar los pasos 1 y 2. Las pantallas abiertas muestran
   «Hay una versión nueva · Actualizar».

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `AccessDenied` en algún paso | LabRole no tiene ese permiso. Si el script no lo resolvió con un aviso `!`, anótalo y sigue con la alternativa de `04` |
| `ExpiredToken` o la consola pide iniciar sesión | La sesión del laboratorio venció: **Start Lab**, abre CloudShell y vuelve a ejecutar `desplegar.sh` (los archivos de CloudShell se conservan) |
| `probar_nube.py`: «ya hay un turno abierto» | Quedó un turno de una pasada que falló a medias. Ciérralo con los eventos `caja/10`, `11` y `12` en la consola, reemplazando `REEMPLAZAR_TURNO_ID` |
| `probar_nube.py`: documento en `pendiente` | El disparador de `dte-emision` o de Streams no está funcionando: Lambda → `emision-dte` / `procesador-eventos` → Aliases → `vivo` → Triggers, y sus logs en CloudWatch |
| `caja/07-autorizadores` y `administracion/04-listar-personal` en 500 | La tabla `configuracion` ya existía sin el índice `GSI1` (creada a mano antes). `desplegar.sh` lo crea al volver a ejecutarlo; en los logs de `caja` aparece `ValidationException ... specified index` |
| `/salud` responde 503 | La función no llega a DynamoDB: revisa sus variables `TABLA_*` y los logs de `salon` |
| `/yo` responde 200 sin token | El autorizador no quedó en esa ruta: ejecuta de nuevo `desplegar.sh` |
| Política del sitio rechazada | *Block Public Access* a nivel de cuenta (riesgo C1 de 04) |
