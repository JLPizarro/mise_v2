"""La tabla de rutas de docs/migracion/02-api-gateway.md coincide con las rutas que atiende el código."""

import re
from pathlib import Path

from funciones.utiles import cargar

DOC = Path(__file__).parents[2] / "docs" / "migracion" / "02-api-gateway.md"
_FILA = re.compile(r"^\| `((?:GET|POST|PATCH|PUT|DELETE) [^`]+)` \| ([a-z\-]+) \| (sí|no) \|", re.MULTILINE)
FUNCIONES_HTTP = ["salon", "pedidos", "caja", "administracion", "reportes", "impresion", "contingencia", "reservas", "mensajeria",
                  "pedidos-externos"]


def test_tabla_de_rutas_igual_al_codigo(nube):
    documentadas = {(ruta, funcion) for ruta, funcion, _ in _FILA.findall(DOC.read_text(encoding="utf-8"))}
    en_codigo = set()
    publicas_en_codigo = set()
    for funcion in FUNCIONES_HTTP:
        for ruta, definicion in cargar(funcion).lambda_handler.rutas.items():
            en_codigo.add((ruta, funcion))
            if definicion.publica:
                publicas_en_codigo.add(ruta)
    assert documentadas == en_codigo
    sin_jwt = {ruta for ruta, _, jwt in _FILA.findall(DOC.read_text(encoding="utf-8")) if jwt == "no"}
    assert sin_jwt == publicas_en_codigo
