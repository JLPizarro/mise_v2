"""Simulador de impresora CloudPRNT: consulta la función `impresion` como lo haría una impresora real,
para validar la impresión desde la nube sin hardware. Solo biblioteca estándar.

Uso (PowerShell):
    $env:POS_CLAVE_IMPRESORA = "mock-clave-cocina"
    python scripts/simulador_impresora.py --api https://<id>.execute-api.us-east-1.amazonaws.com/prod `
        --tenant demo --local local_01 --impresora imp_cocina

Opciones:
    --intervalo 5        segundos entre consultas (las impresoras reales suelen usar 5 a 10)
    --una-vez            consulta una vez, imprime lo que haya y termina (código 0 si imprimió algo)
    --fallar "500 Error" responde con ese código en vez de "200 OK", para probar reintentos

Cada trabajo se muestra en la terminal y se guarda en impresiones/<impresora>/<trabajo>.txt.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def pedir(metodo: str, url: str, basic: str, cuerpo: dict | None = None, query: dict | None = None):
    if query:
        url += "?" + urllib.parse.urlencode(query)
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(url, data=datos, method=metodo,
                                      headers={"authorization": basic, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def ciclo(args, basic: str, url: str, destino: Path) -> bool:
    estado, texto = pedir("POST", url, basic, {"status": "200 OK", "printerMAC": "00:11:62:00:00:00",
                                               "statusCode": "200%20OK", "printingInProgress": False})
    if estado == 401:
        print("✘ credenciales rechazadas (revisa impresora_id y POS_CLAVE_IMPRESORA)")
        sys.exit(2)
    if estado != 200:
        print(f"✘ consulta: HTTP {estado} {texto[:200]}")
        return False
    respuesta = json.loads(texto)
    if not respuesta.get("jobReady"):
        return False
    token = respuesta["jobToken"]
    estado, contenido = pedir("GET", url, basic, query={"token": token, "type": "text/plain"})
    if estado != 200:
        print(f"✘ descarga de {token}: HTTP {estado}")
        return False
    print(f"\n──── trabajo {token} ────\n{contenido}")
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{token}.txt").write_text(contenido, encoding="utf-8")
    codigo = args.fallar or "200 OK"
    estado, texto = pedir("DELETE", url, basic, query={"token": token, "code": codigo})
    print(f"  confirmación ({codigo}): HTTP {estado} {texto}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador de impresora CloudPRNT")
    parser.add_argument("--api", required=True)
    parser.add_argument("--tenant", default="demo")
    parser.add_argument("--local", default="local_01")
    parser.add_argument("--impresora", default="imp_cocina")
    parser.add_argument("--intervalo", type=float, default=5)
    parser.add_argument("--una-vez", action="store_true")
    parser.add_argument("--fallar", help='código de error a informar, p. ej. "500 Error"')
    args = parser.parse_args()
    clave = os.environ.get("POS_CLAVE_IMPRESORA")
    if not clave:
        parser.error("define la variable de entorno POS_CLAVE_IMPRESORA con la clave de la impresora")
    basic = "Basic " + base64.b64encode(f"{args.impresora}:{clave}".encode()).decode()
    url = f"{args.api.rstrip('/')}/impresion/{args.tenant}/{args.local}/{args.impresora}"
    destino = Path("impresiones") / args.impresora
    print(f"Impresora simulada {args.impresora} consultando {url} cada {args.intervalo} s (Ctrl+C para salir)")
    if args.una_vez:
        imprimio = False
        while ciclo(args, basic, url, destino):
            imprimio = True
        return 0 if imprimio else 1
    try:
        while True:
            while ciclo(args, basic, url, destino):
                pass
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
