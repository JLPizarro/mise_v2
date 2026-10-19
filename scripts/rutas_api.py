"""Imprime las rutas del API desde la tabla de docs/migracion/02-api-gateway.md, una por línea:

    METODO<TAB>RUTA<TAB>FUNCION<TAB>si|no      (si = lleva el autorizador JWT)

La tabla es la fuente única: tests/funciones/test_rutas_documentadas.py comprueba que coincide con
las rutas que atiende el código. infra/cloudshell/desplegar.sh crea las rutas a partir de esta salida.
Solo biblioteca estándar (funciona con el Python de CloudShell).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "migracion" / "02-api-gateway.md"
_FILA = re.compile(r"^\| `((?:GET|POST|PATCH|PUT|DELETE) [^`]+)` \| ([a-z\-]+) \| (sí|no) \|", re.MULTILINE)


def rutas(texto: str | None = None) -> list[tuple[str, str, str, bool]]:
    texto = texto if texto is not None else DOC.read_text(encoding="utf-8")
    resultado = []
    for route_key, funcion, jwt in _FILA.findall(texto):
        metodo, ruta = route_key.split(" ", 1)
        resultado.append((metodo, ruta, funcion, jwt == "sí"))
    return resultado


def main() -> int:
    filas = rutas()
    if not filas:
        print("No se encontraron rutas en 02-api-gateway.md", file=sys.stderr)
        return 1
    for metodo, ruta, funcion, jwt in filas:
        print(f"{metodo}\t{ruta}\t{funcion}\t{'si' if jwt else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
