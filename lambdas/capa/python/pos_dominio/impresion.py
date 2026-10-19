"""Contenido de los trabajos de impresión y protocolo CloudPRNT (Star Micronics).

CloudPRNT, en resumen:
1. La impresora hace POST periódico a su URL con su estado. El servidor responde
   {"jobReady": true|false, "mediaTypes": [...], "jobToken": ...}.
2. Si hay trabajo, la impresora hace GET a la misma URL (con ?token=...&type=...) y recibe el
   contenido.
3. Al terminar, hace DELETE (con ?token=...&code=...) para confirmar. Un `code` que empieza en 2
   significa impreso; otro valor es un error de la impresora.

Se envía text/plain de 42 columnas (80 mm). Si el modelo no imprime bien los acentos, la variable
IMPRESION_ASCII=true los quita.
"""

import unicodedata

from pos_dominio import tiempo

ANCHO = 42
TIPO_TEXTO = "text/plain"
MAX_INTENTOS_FALLIDOS = 5


def a_ascii(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def _hora(iso: str | None) -> str:
    if not iso:
        return ""
    return tiempo.desde_iso(iso).astimezone(tiempo.zona_chile()).strftime("%d-%m-%Y %H:%M")


def _linea(izquierda: str, derecha: str = "") -> str:
    espacio = max(ANCHO - len(izquierda) - len(derecha), 1)
    return (izquierda + " " * espacio + derecha)[:ANCHO] if derecha else izquierda[:ANCHO]


def _pesos(monto: int) -> str:
    return "$" + f"{monto:,}".replace(",", ".")


def texto_comanda(trabajo: dict) -> str:
    lineas = [
        "=" * ANCHO,
        f"COMANDA {trabajo.get('cuarto', '')}".upper()[:ANCHO],
        _linea(f"Mesa {trabajo.get('mesa_numero') or trabajo.get('mesa_id')}", trabajo.get("sector") or ""),
        _linea(f"Tanda {trabajo.get('tanda')}", _hora(trabajo.get("creado_en"))),
        f"Garzón: {trabajo.get('garzon', '')}"[:ANCHO],
    ]
    if trabajo.get("origen") == "contingencia":
        lineas.append("** REGISTRADA EN CONTINGENCIA **")
    lineas.append("-" * ANCHO)
    for linea in trabajo.get("lineas", []):
        lineas.append(f"{linea['cantidad']} x {linea['nombre']}"[:ANCHO])
        if linea.get("modificador"):
            lineas.append(f"    + {linea['modificador']}"[:ANCHO])
        if linea.get("observacion"):
            for i in range(0, len(linea["observacion"]), ANCHO - 6):
                lineas.append(f"    * {linea['observacion'][i:i + ANCHO - 6]}")
    lineas += ["=" * ANCHO, "", "", ""]
    return "\n".join(lineas)


def texto_documento(trabajo: dict) -> str:
    detalle = trabajo.get("detalle", {})
    titulo = "FACTURA ELECTRONICA" if trabajo.get("tipo_documento") == "factura" else "BOLETA ELECTRONICA"
    lineas = [
        "=" * ANCHO, titulo, "(DOCUMENTO SIMULADO - SIN VALOR TRIBUTARIO)"[:ANCHO],
        _linea(f"Folio N° {trabajo.get('folio')}", _hora(trabajo.get("emitido_en"))),
    ]
    receptor = trabajo.get("receptor")
    if receptor:
        lineas += [f"RUT: {receptor.get('rut', '')}", receptor.get("razon_social", "")[:ANCHO]]
    lineas.append("-" * ANCHO)
    for item in detalle.get("items", []):
        nombre = item["nombre"] + (f" ({item['modificador']})" if item.get("modificador") else "")
        lineas.append(_linea(f"{item['cantidad']} {nombre}"[:ANCHO - 12], _pesos(item["subtotal"])))
    lineas += ["-" * ANCHO, _linea("TOTAL", _pesos(detalle.get("total", 0)))]
    if detalle.get("propina_total"):
        lineas.append(_linea("Propina (voluntaria)", _pesos(detalle["propina_total"])))
    if trabajo.get("timbre"):
        lineas += ["", f"Timbre: {trabajo['timbre'][:ANCHO - 8]}"]
    if trabajo.get("reimpresion"):
        lineas.append("** REIMPRESION **")
    lineas += ["=" * ANCHO, "", "", ""]
    return "\n".join(lineas)


def contenido(trabajo: dict, *, solo_ascii: bool = False) -> str:
    texto = texto_documento(trabajo) if trabajo.get("tipo") in ("boleta", "factura") else texto_comanda(trabajo)
    return a_ascii(texto) if solo_ascii else texto


def respuesta_consulta(trabajo: dict | None) -> dict:
    """Respuesta al POST periódico de la impresora."""
    if trabajo is None:
        return {"jobReady": False}
    return {"jobReady": True, "mediaTypes": [TIPO_TEXTO], "jobToken": trabajo["trabajo_id"]}


def impreso_ok(codigo: str | None) -> bool:
    return bool(codigo) and str(codigo).strip().startswith("2")
