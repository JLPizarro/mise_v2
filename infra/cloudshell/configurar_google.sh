#!/usr/bin/env bash
# Cuando exista el ID de cliente OAuth de Google: pone la audiencia del autorizador JWT y vuelve a
# desplegar el stage prod. No toca las funciones.
#
# Si el paquete trae la PWA (pwa/dist), también la publica con ese ID de cliente.
#
# Uso:
#   bash infra/cloudshell/configurar_google.sh xxxxxxxx.apps.googleusercontent.com [emisor]
# El emisor por defecto es https://accounts.google.com. Si la página obtener_token.html muestra otro
# (por ejemplo accounts.google.com), pásalo como segundo argumento.
set -euo pipefail
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLIENTE="${1:?Falta el ID de cliente (termina en .apps.googleusercontent.com)}"
EMISOR="${2:-https://accounts.google.com}"
case "$CLIENTE" in *.apps.googleusercontent.com) ;; *) echo "El ID de cliente debe terminar en .apps.googleusercontent.com"; exit 1 ;; esac

API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='pos-api'].ApiId | [0]" --output text)
AUTH_ID=$(aws apigatewayv2 get-authorizers --api-id "$API_ID" --query "Items[?Name=='google-id-token'].AuthorizerId | [0]" --output text)
aws apigatewayv2 update-authorizer --api-id "$API_ID" --authorizer-id "$AUTH_ID" \
  --jwt-configuration "{\"Audience\":[\"${CLIENTE}\"],\"Issuer\":\"${EMISOR}\"}" >/dev/null
aws apigatewayv2 create-deployment --api-id "$API_ID" --stage-name prod --description "audiencia de Google" >/dev/null
echo "✔ autorizador: audiencia ${CLIENTE}, emisor ${EMISOR}; stage prod desplegado"
# El ID queda guardado para que desplegar.sh y publicar_pwa.sh lo usen en cada ejecución.
echo "$CLIENTE" > "$RAIZ/google-client-id.txt"
if [ -f "${PWA_DIST:-$RAIZ/pwa/dist}/index.html" ]; then
  GOOGLE_CLIENT_ID="$CLIENTE" bash "$RAIZ/infra/cloudshell/publicar_pwa.sh"
else
  echo "  (la PWA no está en el paquete: arma pwa/dist en tu PC y ejecuta bash infra/cloudshell/publicar_pwa.sh)"
fi
echo "  Ahora: abre obtener_token.html, copia el token y ejecuta"
echo "  POS_ID_TOKEN=<token> POS_CLAVE_IMPRESORA=mock-clave-cocina python3 scripts/validar_despliegue.py --api https://${API_ID}.execute-api.us-east-1.amazonaws.com/prod"
