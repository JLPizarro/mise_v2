#!/usr/bin/env bash
# Cambia variables de entorno de una función para un simulacro: publica una versión nueva y mueve el
# alias `vivo` a ella. Al final imprime el comando exacto para volver a la versión anterior.
#
# Uso:
#   bash infra/cloudshell/simulacro.sh <función> CLAVE=VALOR [CLAVE=VALOR ...]     (CLAVE= sin valor la quita)
# Ejemplos (docs/migracion/05-validacion.md §5):
#   bash infra/cloudshell/simulacro.sh pedidos SIMULAR_FALLA_DYNAMODB=true        S1: falla de DynamoDB
#   bash infra/cloudshell/simulacro.sh emision-dte DTE_MODO=error5xx              S5: proveedor caído
#   bash infra/cloudshell/simulacro.sh emision-dte DTE_MODO=rechazo               S6: rechazo de negocio
#   bash infra/cloudshell/simulacro.sh emision-dte DTE_MODO=ok                    vuelta a la normalidad
set -euo pipefail
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
FUNCION="${1:?Uso: simulacro.sh <función> CLAVE=VALOR ...}"
shift
[ $# -gt 0 ] || { echo "Indica al menos una variable CLAVE=VALOR"; exit 1; }
TMP="$(mktemp -d)"
aws lambda get-function-configuration --function-name "$FUNCION" --query Environment --output json > "$TMP/actual.json"
python3 - "$TMP/actual.json" "$TMP/nuevo.json" "$@" <<'EOF'
import json, sys
actual = json.load(open(sys.argv[1])) or {}
variables = dict(actual.get("Variables") or {})
for par in sys.argv[3:]:
    clave, _, valor = par.partition("=")
    if valor:
        variables[clave] = valor
    else:
        variables.pop(clave, None)
json.dump({"Variables": variables}, open(sys.argv[2], "w"))
EOF
ANTERIOR=$(aws lambda get-alias --function-name "$FUNCION" --name vivo --query FunctionVersion --output text)
aws lambda update-function-configuration --function-name "$FUNCION" --environment "file://$TMP/nuevo.json" >/dev/null
aws lambda wait function-updated-v2 --function-name "$FUNCION"
VERSION=$(aws lambda publish-version --function-name "$FUNCION" --description "simulacro: $*" --query Version --output text)
aws lambda update-alias --function-name "$FUNCION" --name vivo --function-version "$VERSION" >/dev/null
rm -rf "$TMP"
echo "✔ $FUNCION: vivo en la versión $VERSION con $*"
echo "  Para volver a como estaba:  bash infra/cloudshell/revertir.sh $FUNCION $ANTERIOR"
