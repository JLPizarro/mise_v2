#!/usr/bin/env bash
# Publica la PWA (pwa/dist) en el bucket del sitio, con el config.json de la nube. Idempotente.
#
# Uso, desde la carpeta descomprimida del paquete, después de desplegar.sh:
#   bash infra/cloudshell/publicar_pwa.sh
#   GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com bash infra/cloudshell/publicar_pwa.sh
# El ID de cliente sale de GOOGLE_CLIENT_ID o de google-client-id.txt (lo deja configurar_google.sh).
# Lee valores-despliegue.env (bucket y URL del API). pwa/dist se arma en tu PC: cd pwa && npm ci && npm run build.
#
# Orden de subida: lo que no cambia entre versiones primero (assets con hash, inmutables) y al final
# index.html, para que nadie vea un index que apunte a archivos que todavía no existen. Sin --delete:
# los assets de la versión anterior siguen disponibles para quien aún tenga la página abierta.

set -euo pipefail
export AWS_DEFAULT_REGION=us-east-1
export AWS_PAGER=""

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"
VALORES="$RAIZ/valores-despliegue.env"
DIST="${PWA_DIST:-$RAIZ/pwa/dist}"   # PWA_DIST solo lo usan las pruebas locales

[ -f "$VALORES" ] || { echo "ERROR: falta valores-despliegue.env. Ejecuta antes infra/cloudshell/desplegar.sh"; exit 1; }
CLIENTE_ENTORNO="${GOOGLE_CLIENT_ID:-}"   # valores-despliegue.env trae GOOGLE_CLIENT_ID (a veces vacío): no debe pisar al entorno
# shellcheck disable=SC1090
. "$VALORES"
: "${BUCKET_SITIO:?valores-despliegue.env no tiene BUCKET_SITIO}"
: "${URL_API:?valores-despliegue.env no tiene URL_API}"
: "${URL_SITIO:?valores-despliegue.env no tiene URL_SITIO}"
[ -f "$DIST/index.html" ] || {
  echo "ERROR: falta pwa/dist/index.html. En tu PC ejecuta  cd pwa && npm ci && npm run build  y vuelve a armar el paquete."
  exit 1
}

CLIENTE="${CLIENTE_ENTORNO:-${GOOGLE_CLIENT_ID:-}}"   # entorno, luego valores-despliegue.env, luego el archivo
if [ -z "$CLIENTE" ] && [ -f "$RAIZ/google-client-id.txt" ]; then
  CLIENTE="$(tr -d '[:space:]' < "$RAIZ/google-client-id.txt")"
fi
[ -n "$CLIENTE" ] || echo "    ! sin ID de cliente de Google: la PWA se publica, pero no se podrá ingresar hasta ejecutar configurar_google.sh"

# El config.json se escribe fuera de pwa/dist: así nunca queda una dirección en lo que se versiona o empaqueta.
TMP_PWA="$(mktemp -d)"
trap 'rm -rf "$TMP_PWA"' EXIT
python3 -c 'import json, sys; print(json.dumps({"api_url": sys.argv[1], "google_client_id": sys.argv[2], "modo_dev": False}))' \
  "$URL_API" "$CLIENTE" > "$TMP_PWA/config.json"

DESTINO="s3://${BUCKET_SITIO}"
echo "==> Publicando la PWA en $DESTINO"

# 1. Assets con hash en el nombre: nunca cambian.
if [ -d "$DIST/assets" ]; then
  aws s3 sync "$DIST/assets" "$DESTINO/assets" --cache-control "public,max-age=31536000,immutable" >/dev/null
fi
# 2. El resto de lo estático.
aws s3 sync "$DIST" "$DESTINO" --exclude "assets/*" --exclude config.json --exclude index.html --exclude sw.js \
  --exclude precache.json --exclude manifest.webmanifest --cache-control "public,max-age=86400" >/dev/null
# 3. Lo que debe revalidarse siempre: manifiesto, service worker, lista de precarga y configuración.
aws s3 cp "$DIST/manifest.webmanifest" "$DESTINO/manifest.webmanifest" \
  --content-type "application/manifest+json" --cache-control no-cache >/dev/null
aws s3 cp "$DIST/sw.js" "$DESTINO/sw.js" --content-type "text/javascript" --cache-control no-cache >/dev/null
aws s3 cp "$DIST/precache.json" "$DESTINO/precache.json" --content-type "application/json" --cache-control no-cache >/dev/null
aws s3 cp "$TMP_PWA/config.json" "$DESTINO/config.json" --content-type "application/json" --cache-control no-cache >/dev/null
# 4. Al final, el index.
aws s3 cp "$DIST/index.html" "$DESTINO/index.html" --content-type "text/html; charset=utf-8" --cache-control no-cache >/dev/null

echo "    ✔ PWA publicada"
echo "PWA: ${URL_SITIO}/index.html"
