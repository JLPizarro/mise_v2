#!/usr/bin/env bash
# Despliegue completo del POS desde AWS CloudShell (Learner Lab, us-east-1).
#
# Uso, desde la carpeta descomprimida del paquete:
#   bash infra/cloudshell/desplegar.sh 2>&1 | tee despliegue.log
#
# Variables opcionales (antes de ejecutar):
#   export EMAIL_AVISOS=correo@ejemplo.cl       suscribe ese correo a los dos temas de SNS
#   export EMAIL_DUENO_REAL=dueno@gmail.com     deja su invitación de dueño en la semilla
#   export GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com   audiencia del autorizador (si no, PENDIENTE)
#   export SIN_SEMILLA=1                        no carga los datos mock
#
# Es idempotente: si la sesión se corta, vuelve a ejecutarlo. Lo que ya existe se actualiza; cada
# función publica una versión nueva y mueve su alias `vivo` (la anterior queda para revertir).
# Al terminar deja los valores en valores-despliegue.env y la URL del API.

set -euo pipefail
export AWS_DEFAULT_REGION=us-east-1
export AWS_PAGER=""

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"
TMP="${POS_TMP:-$(mktemp -d)}"   # POS_TMP solo lo usan las pruebas locales
mkdir -p "$TMP"
AY="python3 infra/cloudshell/ayudante.py"
VALORES="$RAIZ/valores-despliegue.env"

paso()  { echo; echo "==> $*"; }
ok()    { echo "    ✔ $*"; }
aviso() { echo "    ! $*"; }
guardar() { echo "$1=\"$2\"" >> "$VALORES"; }

CUENTA=$(aws sts get-caller-identity --query Account --output text)
ROL="arn:aws:iam::${CUENTA}:role/LabRole"
SITIO="pos-sitio-${CUENTA}"
ARCHIVO="pos-archivo-${CUENTA}"
URL_SITIO="https://${SITIO}.s3.us-east-1.amazonaws.com"
: > "$VALORES"
guardar CUENTA "$CUENTA"
# El ID de cliente de Google puede venir del entorno o de google-client-id.txt (lo deja configurar_google.sh).
if [ -z "${GOOGLE_CLIENT_ID:-}" ] && [ -f "$RAIZ/google-client-id.txt" ]; then
  GOOGLE_CLIENT_ID="$(tr -d '[:space:]' < "$RAIZ/google-client-id.txt")"
fi
guardar GOOGLE_CLIENT_ID "${GOOGLE_CLIENT_ID:-}"
echo "Cuenta $CUENTA · región us-east-1 · rol LabRole"

# ---------------------------------------------------------------------------------------------------
paso "0. Paquetes de Lambda"
python3 scripts/construir_capa.py

# ---------------------------------------------------------------------------------------------------
paso "1. Cuota de concurrencia de Lambda"
LIMITE=$(aws lambda get-account-settings --query AccountLimit.ConcurrentExecutions --output text)
ok "ejecuciones simultáneas permitidas: $LIMITE"
guardar CUOTA_CONCURRENCIA "$LIMITE"

# ---------------------------------------------------------------------------------------------------
paso "2. S3: archivo (privado) y sitio (lectura pública por HTTPS)"
crear_bucket() {
  if aws s3api head-bucket --bucket "$1" >/dev/null 2>&1; then ok "$1 ya existe"
  else aws s3api create-bucket --bucket "$1" >/dev/null; ok "$1 creado"; fi
}
crear_bucket "$ARCHIVO"
crear_bucket "$SITIO"
aws s3api put-public-access-block --bucket "$ARCHIVO" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-public-access-block --bucket "$SITIO" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false
cat > "$TMP/politica.json" <<EOF
{"Version":"2012-10-17","Statement":[{"Sid":"LecturaPublicaDelSitio","Effect":"Allow","Principal":"*",
"Action":"s3:GetObject","Resource":"arn:aws:s3:::${SITIO}/*"}]}
EOF
if aws s3api put-bucket-policy --bucket "$SITIO" --policy "file://$TMP/politica.json"; then ok "política pública del sitio"
else aviso "no se pudo aplicar la política pública (riesgo C1 de 04): revisa Block Public Access de la cuenta"; fi
aws s3 cp scripts/obtener_token.html "s3://${SITIO}/obtener_token.html" \
  --content-type "text/html; charset=utf-8" --cache-control no-cache >/dev/null
ok "sitio: ${URL_SITIO}/obtener_token.html"
guardar BUCKET_SITIO "$SITIO"; guardar BUCKET_ARCHIVO "$ARCHIVO"; guardar URL_SITIO "$URL_SITIO"

# ---------------------------------------------------------------------------------------------------
paso "3. DynamoDB: configuracion y operacion"
cat > "$TMP/gsi-configuracion.json" <<'EOF'
[{"IndexName":"GSI1","KeySchema":[{"AttributeName":"GSI1PK","KeyType":"HASH"},{"AttributeName":"GSI1SK","KeyType":"RANGE"}],
  "Projection":{"ProjectionType":"INCLUDE","NonKeyAttributes":["nombre","email","rol","estado","sub","tipo_item"]}}]
EOF
cat > "$TMP/gsi-operacion.json" <<'EOF'
[{"IndexName":"GSI1","KeySchema":[{"AttributeName":"GSI1PK","KeyType":"HASH"},{"AttributeName":"GSI1SK","KeyType":"RANGE"}],
  "Projection":{"ProjectionType":"ALL"}}]
EOF
crear_tabla() {
  local nombre=$1; shift
  if aws dynamodb describe-table --table-name "$nombre" >/dev/null 2>&1; then ok "$nombre ya existe"
  else
    aws dynamodb create-table --table-name "$nombre" --billing-mode PAY_PER_REQUEST \
      --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
                              AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S \
      --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
      --global-secondary-indexes "file://$TMP/gsi-$nombre.json" --deletion-protection-enabled "$@" >/dev/null
    ok "$nombre creada"
  fi
  aws dynamodb wait table-exists --table-name "$nombre"
}
# Una tabla creada antes (por ejemplo, a mano en la consola) puede no tener el índice: sin él, la lista
# de personal y de autorizadores responde 500. Se crea y se espera a que quede activo.
asegurar_gsi() {
  local nombre=$1 estado
  local consulta="Table.GlobalSecondaryIndexes[?IndexName=='GSI1'].IndexStatus | [0]"
  estado=$(aws dynamodb describe-table --table-name "$nombre" --query "$consulta" --output text)
  if [ "$estado" = "None" ]; then
    python3 -c 'import json,sys; print(json.dumps([{"Create": i} for i in json.load(open(sys.argv[1]))]))' \
      "$TMP/gsi-$nombre.json" > "$TMP/gsi-crear-$nombre.json"
    aws dynamodb update-table --table-name "$nombre" \
      --attribute-definitions AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S \
      --global-secondary-index-updates "file://$TMP/gsi-crear-$nombre.json" >/dev/null
    aviso "$nombre no tenía el índice GSI1: creándolo (unos minutos)"
  fi
  until [ "$(aws dynamodb describe-table --table-name "$nombre" --query "$consulta" --output text)" = "ACTIVE" ]; do
    sleep 15
  done
  ok "$nombre: índice GSI1 activo"
}
crear_tabla configuracion
crear_tabla operacion --stream-specification StreamEnabled=true,StreamViewType=NEW_IMAGE
asegurar_gsi configuracion
asegurar_gsi operacion
VISTA=$(aws dynamodb describe-table --table-name operacion --query 'Table.StreamSpecification.StreamViewType' --output text)
if [ "$VISTA" = "None" ]; then
  aws dynamodb update-table --table-name operacion --stream-specification StreamEnabled=true,StreamViewType=NEW_IMAGE >/dev/null
  aws dynamodb wait table-exists --table-name operacion
  VISTA=NEW_IMAGE
fi
[ "$VISTA" = "NEW_IMAGE" ] || { echo "ERROR: el stream de operacion es $VISTA y debe ser NEW_IMAGE (riesgo D2 de 04)"; exit 1; }
ok "stream de operacion: NEW_IMAGE"
TTL=$(aws dynamodb describe-time-to-live --table-name operacion --query 'TimeToLiveDescription.TimeToLiveStatus' --output text)
if [ "$TTL" = "DISABLED" ]; then
  aws dynamodb update-time-to-live --table-name operacion --time-to-live-specification Enabled=true,AttributeName=expira_en >/dev/null
fi
ok "TTL de operacion sobre expira_en"
STREAM_ARN=$(aws dynamodb describe-table --table-name operacion --query Table.LatestStreamArn --output text)

# ---------------------------------------------------------------------------------------------------
paso "4. SQS: colas y colas de fallidos (desde el catálogo central pos_dominio/mensajeria.py)"
crear_cola() {  # nombre CLAVE=VALOR...   → imprime la URL
  local nombre=$1; shift
  local archivo="$TMP/cola-$nombre.json" url
  $AY atributos "$archivo" "$@"
  if url=$(aws sqs get-queue-url --queue-name "$nombre" --query QueueUrl --output text 2>/dev/null); then
    python3 -c 'import json,sys;a=json.load(open(sys.argv[1]));a.pop("FifoQueue",None);json.dump(a,open(sys.argv[1],"w"))' "$archivo"
    aws sqs set-queue-attributes --queue-url "$url" --attributes "file://$archivo"
  else
    url=$(aws sqs create-queue --queue-name "$nombre" --attributes "file://$archivo" --query QueueUrl --output text)
  fi
  echo "$url"
}
arn_cola() { aws sqs get-queue-attributes --queue-url "$1" --attribute-names QueueArn --query Attributes.QueueArn --output text; }
CATORCE_DIAS=1209600
# Nombres, visibilidad, colas de fallidos y número de recepciones salen del catálogo: cambiar una cola es
# cambiar el catálogo, y las pruebas comprueban que la documentación (02) dice lo mismo.
declare -A URL_COLA NOMBRE_COLA
NOMBRES_COLAS=""
while IFS=$'\t' read -r id nombre fifo visibilidad recepciones fallidos; do
  fallidos="${fallidos%$'\r'}"
  ATR=(VisibilityTimeout="$visibilidad" MessageRetentionPeriod=$CATORCE_DIAS)
  if [ "$fifo" = "si" ]; then ATR+=(FifoQueue=true ContentBasedDeduplication=false); fi
  if [ "$fallidos" != "-" ]; then
    ATR+=("RedrivePolicy=$($AY redrive "$(arn_cola "${URL_COLA[$fallidos]}")" "$recepciones")")
  fi
  URL_COLA[$id]=$(crear_cola "$nombre" "${ATR[@]}")
  NOMBRE_COLA[$id]=$nombre
  NOMBRES_COLAS="$NOMBRES_COLAS $nombre"
done < <($AY canales)
URL_DTE=${URL_COLA[dte-emision]}; URL_CONT=${URL_COLA[contingencia-comandas]}
URL_EVT_FALLIDOS=${URL_COLA[procesador-eventos-fallidos]}
ARN_DTE=$(arn_cola "$URL_DTE"); ARN_CONT=$(arn_cola "$URL_CONT"); ARN_EVT_FALLIDOS=$(arn_cola "$URL_EVT_FALLIDOS")
ok "colas del catálogo:$NOMBRES_COLAS"
guardar COLA_DTE_URL "$URL_DTE"; guardar COLA_CONTINGENCIA_URL "$URL_CONT"

# ---------------------------------------------------------------------------------------------------
paso "5. SNS: temas de aviso"
TEMA_DUENO=$(aws sns create-topic --name pos-avisos-dueno --query TopicArn --output text)
TEMA_ALERTAS=$(aws sns create-topic --name pos-alertas-tecnicas --query TopicArn --output text)
if [ -n "${EMAIL_AVISOS:-}" ]; then
  for tema in "$TEMA_DUENO" "$TEMA_ALERTAS"; do
    aws sns subscribe --topic-arn "$tema" --protocol email --notification-endpoint "$EMAIL_AVISOS" >/dev/null
  done
  aviso "revisa ${EMAIL_AVISOS}: hay que pulsar «Confirm subscription» en los 2 correos de AWS"
else
  aviso "sin EMAIL_AVISOS: nadie recibirá los avisos (puedes suscribir correos después en SNS)"
fi
ok "pos-avisos-dueno y pos-alertas-tecnicas"
guardar TEMA_DUENO_ARN "$TEMA_DUENO"; guardar TEMA_ALERTAS_ARN "$TEMA_ALERTAS"

# ---------------------------------------------------------------------------------------------------
paso "6. CloudWatch: grupos de logs con retención de 7 días"
FUNCIONES_API="salon pedidos caja administracion reportes impresion contingencia reservas pedidos-externos mensajeria"
FUNCIONES_ASYNC="procesador-eventos emision-dte drenador-contingencia tareas-programadas"
for grupo in $FUNCIONES_API $FUNCIONES_ASYNC semilla; do
  aws logs create-log-group --log-group-name "/aws/lambda/$grupo" 2>/dev/null || true
  aws logs put-retention-policy --log-group-name "/aws/lambda/$grupo" --retention-in-days 7
done
aws logs create-log-group --log-group-name /aws/apigateway/pos-api 2>/dev/null || true
aws logs put-retention-policy --log-group-name /aws/apigateway/pos-api --retention-in-days 7
ok "$(echo $FUNCIONES_API $FUNCIONES_ASYNC semilla | wc -w) grupos con retención de 7 días"

# ---------------------------------------------------------------------------------------------------
paso "7. Capa pos-dominio"
CAPA_ARN=$(aws lambda publish-layer-version --layer-name pos-dominio --zip-file fileb://dist/capa-pos-dominio.zip \
  --compatible-runtimes python3.12 --compatible-architectures arm64 --query LayerVersionArn --output text)
ok "$CAPA_ARN"
guardar CAPA_ARN "$CAPA_ARN"

# ---------------------------------------------------------------------------------------------------
paso "8. Funciones (versión publicada + alias vivo)"
TABLAS=(TABLA_OPERACION=operacion TABLA_CONFIGURACION=configuracion)
SECRETO=$(aws lambda get-function-configuration --function-name pedidos-externos \
  --query 'Environment.Variables.SECRETO_WEBHOOK' --output text 2>/dev/null || echo None)
if [ "$SECRETO" = "None" ] || [ -z "$SECRETO" ]; then SECRETO=$(python3 -c 'import secrets;print(secrets.token_hex(32))'); fi

desplegar_funcion() {  # nombre segundos megabytes zip CLAVE=VALOR...
  local nombre=$1 tiempo=$2 memoria=$3 zip=$4; shift 4
  local entorno="$TMP/entorno-$nombre.json" version anterior
  $AY variables "$entorno" "$@"
  if aws lambda get-function --function-name "$nombre" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "$nombre" --zip-file "fileb://$zip" >/dev/null
    aws lambda wait function-updated-v2 --function-name "$nombre"
    aws lambda update-function-configuration --function-name "$nombre" --role "$ROL" --runtime python3.12 \
      --handler lambda_function.lambda_handler --timeout "$tiempo" --memory-size "$memoria" \
      --layers "$CAPA_ARN" --environment "file://$entorno" >/dev/null
  else
    aws lambda create-function --function-name "$nombre" --role "$ROL" --runtime python3.12 --architectures arm64 \
      --handler lambda_function.lambda_handler --timeout "$tiempo" --memory-size "$memoria" \
      --layers "$CAPA_ARN" --environment "file://$entorno" --zip-file "fileb://$zip" >/dev/null
    aws lambda wait function-active-v2 --function-name "$nombre"
  fi
  aws lambda wait function-updated-v2 --function-name "$nombre"
  version=$(aws lambda publish-version --function-name "$nombre" --description "despliegue $(date -u +%FT%TZ)" \
    --query Version --output text)
  if anterior=$(aws lambda get-alias --function-name "$nombre" --name vivo --query FunctionVersion --output text 2>/dev/null); then
    aws lambda update-alias --function-name "$nombre" --name vivo --function-version "$version" >/dev/null
  else
    anterior="-"
    aws lambda create-alias --function-name "$nombre" --name vivo --function-version "$version" >/dev/null
  fi
  ok "$nombre: versión $version en vivo (anterior: $anterior)"
  guardar "VERSION_${nombre//-/_}" "$version"
  guardar "ANTERIOR_${nombre//-/_}" "$anterior"
}
F=dist/funciones
desplegar_funcion salon 10 256 $F/salon.zip "${TABLAS[@]}"
desplegar_funcion pedidos 10 256 $F/pedidos.zip "${TABLAS[@]}" COLA_CONTINGENCIA_URL="$URL_CONT"
desplegar_funcion caja 10 512 $F/caja.zip "${TABLAS[@]}"
desplegar_funcion administracion 10 512 $F/administracion.zip "${TABLAS[@]}"
desplegar_funcion reportes 10 256 $F/reportes.zip "${TABLAS[@]}"
desplegar_funcion impresion 10 256 $F/impresion.zip "${TABLAS[@]}"
desplegar_funcion contingencia 10 128 $F/contingencia.zip COLA_CONTINGENCIA_URL="$URL_CONT"
desplegar_funcion reservas 10 128 $F/reservas.zip "${TABLAS[@]}"
desplegar_funcion pedidos-externos 10 128 $F/pedidos-externos.zip "${TABLAS[@]}" SECRETO_WEBHOOK="$SECRETO"
desplegar_funcion mensajeria 15 256 $F/mensajeria.zip "${TABLAS[@]}" TEMA_DUENO_ARN="$TEMA_DUENO"
desplegar_funcion procesador-eventos 60 256 $F/procesador-eventos.zip "${TABLAS[@]}" BUCKET_ARCHIVO="$ARCHIVO" \
  COLA_DTE_URL="$URL_DTE" TEMA_DUENO_ARN="$TEMA_DUENO" TEMA_ALERTAS_ARN="$TEMA_ALERTAS"
desplegar_funcion emision-dte 30 256 $F/emision-dte.zip "${TABLAS[@]}" COLA_DTE_URL="$URL_DTE" MAX_RECEPCIONES=5 \
  DTE_MODO=ok DTE_TASA_FALLA=1 DTE_LATENCIA_MS=0
desplegar_funcion drenador-contingencia 30 256 $F/drenador-contingencia.zip "${TABLAS[@]}"
desplegar_funcion tareas-programadas 60 256 $F/tareas-programadas.zip "${TABLAS[@]}" COLA_DTE_URL="$URL_DTE" \
  TEMA_DUENO_ARN="$TEMA_DUENO" TEMA_ALERTAS_ARN="$TEMA_ALERTAS"

if [ "$LIMITE" -ge 100 ]; then
  aws lambda put-function-concurrency --function-name contingencia --reserved-concurrent-executions 5 >/dev/null
  ok "concurrencia reservada 5 para contingencia"
else
  aviso "cuota de concurrencia $LIMITE: no se reserva concurrencia (riesgo L2 de 04)"
fi

# ---------------------------------------------------------------------------------------------------
paso "9. Disparadores (sobre el alias vivo)"
mapeo_existe() {
  local uuid
  uuid=$(aws lambda list-event-source-mappings --function-name "$1:vivo" --event-source-arn "$2" \
    --query 'EventSourceMappings[0].UUID' --output text)
  [ -n "$uuid" ] && [ "$uuid" != "None" ]
}
$AY filtro_streams "$TMP/filtro.json"
$AY destino_fallo "$TMP/destino.json" "$ARN_EVT_FALLIDOS"
if mapeo_existe procesador-eventos "$STREAM_ARN"; then ok "Streams → procesador-eventos ya existe"
else
  COMUN=(--function-name procesador-eventos:vivo --event-source-arn "$STREAM_ARN" --starting-position LATEST
         --batch-size 100 --maximum-batching-window-in-seconds 1 --bisect-batch-on-function-error
         --maximum-retry-attempts 10 --maximum-record-age-in-seconds 3600
         --function-response-types ReportBatchItemFailures --filter-criteria "file://$TMP/filtro.json")
  if aws lambda create-event-source-mapping "${COMUN[@]}" --destination-config "file://$TMP/destino.json" >/dev/null; then
    ok "Streams → procesador-eventos (con destino ante fallo)"
  else
    aviso "LabRole no permitió el destino ante fallo (riesgo L1): se crea sin él; la alarma del iterador avisa"
    aws lambda create-event-source-mapping "${COMUN[@]}" >/dev/null
    ok "Streams → procesador-eventos"
  fi
fi
if mapeo_existe emision-dte "$ARN_DTE"; then ok "${NOMBRE_COLA[dte-emision]} → emision-dte ya existe"
else
  aws lambda create-event-source-mapping --function-name emision-dte:vivo --event-source-arn "$ARN_DTE" \
    --batch-size 5 --function-response-types ReportBatchItemFailures --scaling-config MaximumConcurrency=2 >/dev/null
  ok "${NOMBRE_COLA[dte-emision]} → emision-dte (lote 5, concurrencia máxima 2)"
fi
if mapeo_existe drenador-contingencia "$ARN_CONT"; then ok "contingencia → drenador ya existe"
else
  aws lambda create-event-source-mapping --function-name drenador-contingencia:vivo --event-source-arn "$ARN_CONT" \
    --batch-size 10 --function-response-types ReportBatchItemFailures >/dev/null
  ok "${NOMBRE_COLA[contingencia-comandas]} → drenador-contingencia"
fi

# ---------------------------------------------------------------------------------------------------
paso "10. EventBridge: regla cada 5 minutos para tareas-programadas"
REGLA_ARN=$(aws events put-rule --name pos-tareas-programadas --schedule-expression "rate(5 minutes)" --state ENABLED \
  --query RuleArn --output text)
aws lambda add-permission --function-name tareas-programadas --qualifier vivo --statement-id eventbridge-pos-tareas \
  --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$REGLA_ARN" >/dev/null 2>&1 || true
aws events put-targets --rule pos-tareas-programadas \
  --targets "Id=tareas,Arn=arn:aws:lambda:us-east-1:${CUENTA}:function:tareas-programadas:vivo" >/dev/null
ok "pos-tareas-programadas → tareas-programadas:vivo"

# ---------------------------------------------------------------------------------------------------
if [ -z "${SIN_SEMILLA:-}" ]; then
  paso "11. Datos mock (herramienta temporal semilla)"
  aws lambda delete-function --function-name semilla >/dev/null 2>&1 || true
  EXTRA=()
  [ -n "${EMAIL_DUENO_REAL:-}" ] && EXTRA=(EMAIL_DUENO_REAL="$EMAIL_DUENO_REAL")
  $AY variables "$TMP/entorno-semilla.json" "${TABLAS[@]}" "${EXTRA[@]}"
  aws lambda create-function --function-name semilla --role "$ROL" --runtime python3.12 --architectures arm64 \
    --handler lambda_function.lambda_handler --timeout 60 --memory-size 512 --layers "$CAPA_ARN" \
    --environment "file://$TMP/entorno-semilla.json" --zip-file fileb://dist/herramientas/semilla.zip >/dev/null
  aws lambda wait function-active-v2 --function-name semilla
  aws lambda invoke --function-name semilla --cli-binary-format raw-in-base64-out --payload '{}' "$TMP/semilla.json" >/dev/null
  ok "$(cat "$TMP/semilla.json")"
  aws lambda delete-function --function-name semilla
  ok "función semilla borrada"
fi

# ---------------------------------------------------------------------------------------------------
paso "12. API Gateway: pos-api"
$AY cors "$TMP/cors.json" "$URL_SITIO" "http://localhost:8000"
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='pos-api'].ApiId | [0]" --output text)
if [ -z "$API_ID" ] || [ "$API_ID" = "None" ]; then
  API_ID=$(aws apigatewayv2 create-api --name pos-api --protocol-type HTTP --cors-configuration "file://$TMP/cors.json" \
    --query ApiId --output text)
  ok "API creada: $API_ID"
else
  aws apigatewayv2 update-api --api-id "$API_ID" --cors-configuration "file://$TMP/cors.json" >/dev/null
  ok "API existente: $API_ID (CORS actualizado)"
fi
guardar API_ID "$API_ID"

EMISOR="${GOOGLE_EMISOR:-https://accounts.google.com}"
AUTH_ID=$(aws apigatewayv2 get-authorizers --api-id "$API_ID" --query "Items[?Name=='google-id-token'].AuthorizerId | [0]" --output text)
if [ -z "$AUTH_ID" ] || [ "$AUTH_ID" = "None" ]; then
  $AY jwt "$TMP/jwt.json" "${GOOGLE_CLIENT_ID:-PENDIENTE}" "$EMISOR"
  AUTH_ID=$(aws apigatewayv2 create-authorizer --api-id "$API_ID" --name google-id-token --authorizer-type JWT \
    --identity-source '$request.header.Authorization' --jwt-configuration "file://$TMP/jwt.json" \
    --query AuthorizerId --output text)
  ok "autorizador JWT creado (audiencia ${GOOGLE_CLIENT_ID:-PENDIENTE})"
elif [ -n "${GOOGLE_CLIENT_ID:-}" ]; then
  $AY jwt "$TMP/jwt.json" "$GOOGLE_CLIENT_ID" "$EMISOR"
  aws apigatewayv2 update-authorizer --api-id "$API_ID" --authorizer-id "$AUTH_ID" --jwt-configuration "file://$TMP/jwt.json" >/dev/null
  ok "autorizador JWT actualizado con el ID de cliente"
else
  ok "autorizador JWT ya existe (no se cambia su audiencia)"
fi

declare -A INTEGRACION
aws apigatewayv2 get-integrations --api-id "$API_ID" > "$TMP/integraciones.json"
for funcion in $FUNCIONES_API; do
  uri="arn:aws:lambda:us-east-1:${CUENTA}:function:${funcion}:vivo"
  id=$($AY buscar "$TMP/integraciones.json" IntegrationUri "$uri" IntegrationId)
  if [ -z "$id" ]; then
    id=$(aws apigatewayv2 create-integration --api-id "$API_ID" --integration-type AWS_PROXY --integration-uri "$uri" \
      --payload-format-version 2.0 --query IntegrationId --output text)
  fi
  INTEGRACION[$funcion]=$id
  aws lambda add-permission --function-name "$funcion" --qualifier vivo --statement-id "apigw-${API_ID}" \
    --action lambda:InvokeFunction --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:us-east-1:${CUENTA}:${API_ID}/*" >/dev/null 2>&1 || true
done
ok "${#INTEGRACION[@]} integraciones al alias vivo (formato 2.0) con permiso de invocación"

aws apigatewayv2 get-routes --api-id "$API_ID" > "$TMP/rutas.json"
N=0
while IFS=$'\t' read -r metodo ruta funcion jwt; do
  jwt="${jwt%$'\r'}"   # por si la salida trae finales de línea de Windows
  clave="$metodo $ruta"
  if [ "$jwt" = "si" ]; then AUT=(--authorization-type JWT --authorizer-id "$AUTH_ID"); else AUT=(--authorization-type NONE); fi
  id=$($AY buscar "$TMP/rutas.json" RouteKey "$clave" RouteId)
  if [ -z "$id" ]; then
    aws apigatewayv2 create-route --api-id "$API_ID" --route-key "$clave" --target "integrations/${INTEGRACION[$funcion]}" \
      "${AUT[@]}" >/dev/null
  else
    aws apigatewayv2 update-route --api-id "$API_ID" --route-id "$id" --target "integrations/${INTEGRACION[$funcion]}" \
      "${AUT[@]}" >/dev/null
  fi
  N=$((N + 1))
done < <(python3 scripts/rutas_api.py)
ok "$N rutas (las públicas sin autorizador)"

GRUPO_ARN=$(aws logs describe-log-groups --log-group-name-prefix /aws/apigateway/pos-api \
  --query 'logGroups[0].arn' --output text | sed 's/:\*$//')
$AY registro_acceso "$TMP/registro.json" "$GRUPO_ARN"
$AY limites_rutas "$TMP/limites.json"
# Sin despliegue automático: un cambio a medias no queda publicado; se publica al final con create-deployment.
ETAPA=(--api-id "$API_ID" --stage-name prod --no-auto-deploy
       --default-route-settings ThrottlingRateLimit=50,ThrottlingBurstLimit=100 --route-settings "file://$TMP/limites.json")
if aws apigatewayv2 get-stage --api-id "$API_ID" --stage-name prod >/dev/null 2>&1; then ACCION=update-stage; else ACCION=create-stage; fi
if aws apigatewayv2 "$ACCION" "${ETAPA[@]}" --access-log-settings "file://$TMP/registro.json" >/dev/null 2>"$TMP/etapa.err"; then
  ok "stage prod: sin despliegue automático, límites de tasa y registro de acceso"
else
  aviso "registro de acceso no permitido ($(head -c 200 "$TMP/etapa.err")) — riesgo A7: se configura sin él"
  aws apigatewayv2 "$ACCION" "${ETAPA[@]}" >/dev/null
  ok "stage prod: sin despliegue automático y con límites de tasa"
fi
aws apigatewayv2 create-deployment --api-id "$API_ID" --stage-name prod --description "despliegue $(date -u +%FT%TZ)" >/dev/null
URL_API="https://${API_ID}.execute-api.us-east-1.amazonaws.com/prod"
ok "desplegado en $URL_API"
guardar URL_API "$URL_API"

# ---------------------------------------------------------------------------------------------------
paso "13. Athena: tabla del archivo histórico"
CANTIDAD=$($AY sentencias_sql infra/athena/eventos.sql "$ARCHIVO" "$TMP/sql")
for i in $(seq 1 "$CANTIDAD"); do
  QID=$(aws athena start-query-execution --query-string "$(cat "$TMP/sql/$i.sql")" \
    --result-configuration "OutputLocation=s3://${ARCHIVO}/athena-resultados/" --query QueryExecutionId --output text)
  for _ in $(seq 1 30); do
    ESTADO=$(aws athena get-query-execution --query-execution-id "$QID" --query QueryExecution.Status.State --output text)
    case "$ESTADO" in SUCCEEDED|FAILED|CANCELLED) break ;; esac
    sleep 2
  done
  if [ "$ESTADO" = "SUCCEEDED" ]; then ok "sentencia $i de $CANTIDAD"
  else aviso "sentencia $i: $ESTADO — $(aws athena get-query-execution --query-execution-id "$QID" \
         --query QueryExecution.Status.StateChangeReason --output text)"; fi
done

# ---------------------------------------------------------------------------------------------------
paso "14. Alarmas de CloudWatch → pos-alertas-tecnicas"
alarma() {  # nombre namespace metrica estadistica periodo umbral operador [Name=..,Value=..]
  local nombre=$1 ns=$2 metrica=$3 est=$4 periodo=$5 umbral=$6 op=$7; shift 7
  local dims=()
  [ $# -gt 0 ] && dims=(--dimensions "$@")
  aws cloudwatch put-metric-alarm --alarm-name "$nombre" --namespace "$ns" --metric-name "$metrica" --statistic "$est" \
    --period "$periodo" --evaluation-periods 1 --datapoints-to-alarm 1 --threshold "$umbral" --comparison-operator "$op" \
    --treat-missing-data notBreaching --alarm-actions "$TEMA_ALERTAS" "${dims[@]}"
}
alarma pos-fallidos-dte AWS/SQS ApproximateNumberOfMessagesVisible Maximum 300 1 GreaterThanOrEqualToThreshold \
  Name=QueueName,Value="${NOMBRE_COLA[dte-emision-fallidos]}"
alarma pos-fallidos-contingencia AWS/SQS ApproximateNumberOfMessagesVisible Maximum 300 1 GreaterThanOrEqualToThreshold \
  Name=QueueName,Value="${NOMBRE_COLA[contingencia-comandas-fallidos]}"
alarma pos-fallidos-eventos AWS/SQS ApproximateNumberOfMessagesVisible Maximum 300 1 GreaterThanOrEqualToThreshold \
  Name=QueueName,Value="${NOMBRE_COLA[procesador-eventos-fallidos]}"
alarma pos-dte-atrasado AWS/SQS ApproximateAgeOfOldestMessage Maximum 300 900 GreaterThanThreshold \
  Name=QueueName,Value="${NOMBRE_COLA[dte-emision]}"
alarma pos-contingencia-atrasada AWS/SQS ApproximateAgeOfOldestMessage Maximum 60 300 GreaterThanThreshold \
  Name=QueueName,Value="${NOMBRE_COLA[contingencia-comandas]}"
alarma pos-errores-lambda AWS/Lambda Errors Sum 300 0 GreaterThanThreshold
alarma pos-limitaciones-lambda AWS/Lambda Throttles Sum 300 0 GreaterThanThreshold
alarma pos-iterador-streams AWS/Lambda IteratorAge Maximum 60 60000 GreaterThanThreshold \
  Name=FunctionName,Value=procesador-eventos
$AY alarma_5xx "$TMP/alarma5xx.json" "$API_ID"
aws cloudwatch put-metric-alarm --alarm-name pos-api-5xx --metrics "file://$TMP/alarma5xx.json" --evaluation-periods 1 \
  --datapoints-to-alarm 1 --threshold 1 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching \
  --alarm-actions "$TEMA_ALERTAS"
ok "9 alarmas"

# ---------------------------------------------------------------------------------------------------
PWA_DIST_ACTUAL="${PWA_DIST:-$RAIZ/pwa/dist}"   # PWA_DIST solo lo usan las pruebas locales
URL_PWA="(no publicada: arma pwa/dist en tu PC y ejecuta bash infra/cloudshell/publicar_pwa.sh)"
if [ -f "$PWA_DIST_ACTUAL/index.html" ]; then
  paso "15. PWA"
  bash infra/cloudshell/publicar_pwa.sh
  URL_PWA="$URL_SITIO/index.html"
fi

# ---------------------------------------------------------------------------------------------------
paso "Listo"
cat <<EOF
    API:           $URL_API
    Salud:         $URL_API/salud
    Página token:  $URL_SITIO/obtener_token.html
    PWA:           $URL_PWA
    Valores:       $VALORES

    Siguiente paso:  python3 scripts/probar_nube.py
EOF
rm -rf "$TMP"
