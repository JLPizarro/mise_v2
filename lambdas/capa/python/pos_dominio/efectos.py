"""Efectos de cada evento, calculados sin tocar AWS (los aplica `procesador-eventos`).

El flujo de eventos informa lo que ya ocurrió; nunca decide si algo ocurre.

- Agregados del turno y del día (para reportes; el arqueo usa los totales síncronos del turno).
- Archivo histórico: un JSON comprimido por evento, particionado por cliente y fecha (Athena).
- Comprobante interno de venta en HTML.
- Envío a la cola dte-emision para `venta.cerrada`.
- Avisos al dueño o al equipo técnico por SNS.
"""

import gzip
import html
import json

from pos_dominio import claves, tiempo

TIPOS_CON_AGREGADO = ("venta.cerrada", "retiro.registrado", "pedido.cerrado_sin_venta")


def _pesos(monto: int) -> str:
    signo = "-" if monto < 0 else ""
    return f"{signo}${abs(monto):,}".replace(",", ".")


def fecha_del_evento(evento: dict) -> str:
    return tiempo.fecha_operativa(tiempo.desde_iso(evento["ocurrido_en"]))


def agregados(evento: dict) -> list[tuple[str, str, dict]]:
    """(PK, SK, incrementos) a sumar con ADD. Vacío si el evento no alimenta agregados."""
    tipo, datos = evento["tipo"], evento.get("datos", {})
    L = claves.local(evento["tenant_id"], evento["local_id"])
    if tipo == "venta.cerrada":
        resumen = {"n_ventas": 1, "total_ventas": datos["total"], "total_propinas": datos.get("propina_total", 0)}
        for pago in datos.get("pagos", []):
            resumen[f"monto_{pago['metodo']}"] = resumen.get(f"monto_{pago['metodo']}", 0) + pago["monto"]
            resumen[f"propina_{pago['metodo']}"] = resumen.get(f"propina_{pago['metodo']}", 0) + pago["propina"]
        garzon = {"n_ventas": 1, "total_ventas": datos["total"], "total_propinas": datos.get("propina_total", 0)}
        return [
            (claves.turno(L, datos["turno_id"]), "AGG#RESUMEN", resumen),
            (claves.turno(L, datos["turno_id"]), f"AGG#GARZON#{datos['garzon_id']}", garzon),
            (claves.dia(L, datos["fecha_operativa"]), "AGG#RESUMEN", resumen),
        ]
    if tipo == "retiro.registrado":
        return [(claves.turno(L, datos["turno_id"]), "AGG#RESUMEN", {"n_retiros": 1, "total_retiros": datos["monto"]})]
    if tipo == "pedido.cerrado_sin_venta":
        return [(claves.dia(L, fecha_del_evento(evento)), "AGG#RESUMEN", {"n_cerrados_sin_venta": 1})]
    return []


def clave_archivo(evento: dict) -> str:
    return f"eventos/tenant={evento['tenant_id']}/fecha={fecha_del_evento(evento)}/{evento['event_id']}.json.gz"


def contenido_archivo(evento: dict) -> bytes:
    fila = {k: evento.get(k) for k in ("event_id", "tipo", "v", "tenant_id", "local_id", "ocurrido_en", "registrado_en",
                                         "usuario_id", "command_id", "origen")}
    fila["datos"] = json.dumps(evento.get("datos", {}), ensure_ascii=False, separators=(",", ":"))
    # mtime=0: el mismo evento produce siempre el mismo objeto (reintentos idempotentes).
    return gzip.compress((json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"), mtime=0)


def clave_comprobante(evento: dict) -> str:
    datos = evento["datos"]
    return (f"comprobantes/tenant={evento['tenant_id']}/local={evento['local_id']}/"
            f"fecha={datos['fecha_operativa']}/{datos['venta_id']}.html")


def comprobante_html(evento: dict) -> str:
    datos = evento["datos"]
    e = html.escape
    pesos = _pesos
    filas = "".join(
        f"<tr><td>{e(str(i['cantidad']))}</td><td>{e(i['nombre'])}"
        f"{' (' + e(i['modificador']) + ')' if i.get('modificador') else ''}</td>"
        f"<td class=n>{pesos(i['precio_unitario'])}</td><td class=n>{pesos(i['subtotal'])}</td></tr>"
        for i in datos.get("items", []))
    pagos = "".join(f"<tr><td colspan=3>{e(p['metodo'])}</td><td class=n>{pesos(p['monto'])}"
                    f"{' + propina ' + pesos(p['propina']) if p.get('propina') else ''}</td></tr>"
                    for p in datos.get("pagos", []))
    documento = datos.get("documento") or {}
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Comprobante interno {e(datos['venta_id'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto;color:#222}}
td{{padding:.2rem .4rem;border-bottom:1px solid #eee}}.n{{text-align:right}}</style></head><body>
<h1>Comprobante interno de venta</h1>
<p>No es un documento tributario.</p>
<p>Venta {e(datos['venta_id'])} · Mesa {e(str(datos.get('mesa_id', '')))} · {e(datos.get('cerrado_en', ''))}<br>
Local {e(evento['local_id'])} · Turno {e(datos['turno_id'])} · Documento: {e(documento.get('tipo', '—'))}</p>
<table><thead><tr><th>Cant.</th><th>Producto</th><th>Precio</th><th>Subtotal</th></tr></thead>
<tbody>{filas}</tbody></table>
<p><strong>Total: {pesos(datos['total'])}</strong> · Propina: {pesos(datos.get('propina_total', 0))}</p>
<table><tbody>{pagos}</tbody></table></body></html>"""


def mensaje_dte(evento: dict) -> dict | None:
    if evento["tipo"] != "venta.cerrada":
        return None
    datos = evento["datos"]
    return {"tenant_id": evento["tenant_id"], "local_id": evento["local_id"], "turno_id": datos["turno_id"],
            "venta_id": datos["venta_id"]}


def avisos(evento: dict) -> list[tuple[str, str, str]]:
    """(aviso, asunto, mensaje). El tema de cada aviso lo decide el catálogo (pos_dominio.mensajeria)."""
    tipo, datos = evento["tipo"], evento.get("datos", {})
    lugar = f"Local {evento['local_id']} ({evento['tenant_id']})"
    if tipo == "turno.cerrado":
        r = datos.get("resultado", {})
        if r.get("diferencia_efectivo", 0) != 0:
            exceso = " Supera el umbral." if r.get("fuera_de_umbral") else ""
            return [("cierre_con_diferencia", "MISE: cierre de caja con observaciones",
                     f"{lugar}: el turno {datos['turno_id']} cerró con una diferencia de efectivo de "
                     f"{_pesos(r['diferencia_efectivo'])} (esperado {_pesos(r['efectivo_esperado'])}, "
                     f"contado {_pesos(r['conteo_definitivo'])}).{exceso}")]
    if tipo == "dte.rechazado":
        return [("documento_rechazado", "MISE: documento tributario rechazado",
                 f"{lugar}: la venta {datos.get('venta_id')} fue rechazada por el proveedor: {datos.get('motivo')}")]
    if tipo == "dte.fallido":
        return [("documento_fallido", "MISE: documento tributario fallido",
                 f"{lugar}: la venta {datos.get('venta_id')} agotó sus reintentos y está en la cola de fallidos.")]
    if tipo == "conflicto.registrado":
        return [("comanda_en_conflicto", "MISE: comanda en conflicto tras una contingencia",
                 f"{lugar}: una comanda registrada durante una falla no se pudo aplicar ({datos.get('motivo')}). "
                 f"Revísala en la bandeja de conflictos de la caja.")]
    if tipo == "autorizacion.rechazada" and datos.get("bloqueado"):
        return [("autorizacion_bloqueada", "MISE: autorización bloqueada por intentos fallidos",
                 f"{lugar}: se bloqueó el código de {datos.get('autorizador_id')} tras 5 intentos fallidos "
                 f"(solicitante {datos.get('solicitante_id')}).")]
    return []
