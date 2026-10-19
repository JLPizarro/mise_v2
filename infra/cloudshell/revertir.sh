#!/usr/bin/env bash
# Revierte una función moviendo su alias `vivo` a otra versión publicada. Efecto inmediato: el API
# Gateway y los disparadores apuntan al alias.
#
# Uso:
#   bash infra/cloudshell/revertir.sh pedidos            muestra las versiones y cuál está en vivo
#   bash infra/cloudshell/revertir.sh pedidos 3          mueve vivo a la versión 3
set -euo pipefail
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
FUNCION="${1:?Uso: revertir.sh <función> [versión]}"
ACTUAL=$(aws lambda get-alias --function-name "$FUNCION" --name vivo --query FunctionVersion --output text)
if [ $# -lt 2 ]; then
  echo "En vivo: versión $ACTUAL"
  aws lambda list-versions-by-function --function-name "$FUNCION" \
    --query 'Versions[?Version!=`$LATEST`].[Version, Description, LastModified]' --output table
  exit 0
fi
aws lambda update-alias --function-name "$FUNCION" --name vivo --function-version "$2" >/dev/null
echo "✔ $FUNCION: vivo pasó de la versión $ACTUAL a la $2"
