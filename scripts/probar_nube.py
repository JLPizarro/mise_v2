"""Prueba el despliegue real desde CloudShell, sin Google: invoca cada función (alias vivo) con los
eventos de eventos-prueba en orden, espera los procesos asíncronos reales y prueba la API pública.

Uso, en CloudShell, desde la carpeta del paquete y después de desplegar:
    python3 scripts/probar_nube.py

Solo biblioteca estándar; llama a la AWS CLI que ya trae CloudShell. Se puede ejecutar varias veces:
cada ejecución usa IDs nuevos (pedido, ítems, comandos), así que no choca con la anterior.

Qué comprueba:
  1. Los 43 eventos del flujo de la consola dan el código HTTP esperado (o el lote sin fallos).
  2. Asíncrono real: el documento tributario queda `emitido` (Streams → procesador → SQS → emision-dte)
     y el reporte del turno muestra la venta en los agregados.
  3. Archivo histórico: hay objetos en s3://pos-archivo-<cuenta>/eventos/.
  3b. Mensajería: catálogo central, validación, dos destinos de tipo cola con reglas distintas, un aviso
     de prueba que llega solo al destino con la regla, crear y eliminar una regla, panel de fallidos y
     eliminación de los destinos de prueba.
  4. API pública: /salud responde 200, /yo sin token responde 401 (autorizador activo), y la impresora
     de caja retira la boleta por CloudPRNT a través del API Gateway.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import generar_eventos_prueba as generador  # noqa: E402
import simulador_impresora  # noqa: E402
from validar_despliegue import ulid  # noqa: E402

_FIJO = re.compile(r"01K7H0Z3Q8W4M2N5P6R7S8T9[0-9A-HJKMNP-TV-Z]{2}")


def aws(*argumentos: str) -> str:
    proceso = subprocess.run(["aws", *argumentos], capture_output=True, text=True)
    if proceso.returncode != 0:
        raise RuntimeError(proceso.stderr.strip()[-800:])
    return proceso.stdout


def invocar(funcion: str, evento: dict) -> tuple[object, str | None]:
    with tempfile.TemporaryDirectory() as carpeta:
        entrada, salida = Path(carpeta) / "evento.json", Path(carpeta) / "respuesta.json"
        entrada.write_text(json.dumps(evento), encoding="utf-8")
        try:
            meta = json.loads(aws("lambda", "invoke", "--function-name", f"{funcion}:vivo",
                                  "--cli-binary-format", "raw-in-base64-out", "--payload", f"file://{entrada}",
                                  "--log-type", "Tail", str(salida)))
        except RuntimeError as error:
            return None, str(error)
        resultado = json.loads(salida.read_text(encoding="utf-8") or "null")
        if meta.get("FunctionError"):
            registro = base64.b64decode(meta.get("LogResult", "")).decode("utf-8", "replace")
            return resultado, f"la función falló: {json.dumps(resultado)[:300]}\n{registro[-1200:]}"
        return resultado, None


def cuerpo_de(resultado) -> object:
    texto = (resultado or {}).get("body") or ""
    try:
        return json.loads(texto)
    except ValueError:
        return texto


class Prueba:
    def __init__(self):
        self.fallas = 0
        self.mapa: dict[str, str] = {}
        self.sufijo = time.strftime("%H%M%S")
        self.capturado: dict[str, str] = {}

    def resultado(self, ok: bool, texto: str) -> None:
        print(f"  {'✔' if ok else '✘'} {texto}")
        self.fallas += 0 if ok else 1

    def preparar(self, evento: dict) -> dict:
        texto = json.dumps(evento)
        texto = _FIJO.sub(lambda m: self.mapa.setdefault(m.group(), ulid()), texto)
        texto = texto.replace("Barra exterior", f"Barra exterior {self.sufijo}")
        for marcador, valor in self.capturado.items():
            texto = texto.replace(marcador, valor)
        return json.loads(texto)

    def evento(self, funcion: str, nombre: str) -> dict:
        for f, n, evento, _, _ in generador.FLUJO:
            if (f, n) == (funcion, nombre):
                return self.preparar(evento)
        raise KeyError(nombre)


def flujo(p: Prueba) -> None:
    print("\n1. Flujo de eventos (invocación directa del alias vivo)")
    abierto, _ = invocar("caja", p.evento("caja", "02-turno-actual"))
    if abierto and abierto.get("statusCode") == 200:
        turno = cuerpo_de(abierto).get("turno_id")
        p.resultado(False, f"ya hay un turno abierto ({turno}) de una ejecución anterior. Ciérralo con los eventos "
                           "caja/10, 11 y 12 reemplazando REEMPLAZAR_TURNO_ID, y vuelve a ejecutar")
        return
    for funcion, nombre, _, esperado, comprobar in generador.FLUJO:
        resultado, error = invocar(funcion, p.evento(funcion, nombre))
        if error:
            p.resultado(False, f"{funcion}/{nombre}: {error}")
            continue
        if esperado is None:
            fallidos = (resultado or {}).get("batchItemFailures", [])
            p.resultado(not fallidos, f"{funcion}/{nombre}: {comprobar}" + (f" → {fallidos}" if fallidos else ""))
            continue
        cuerpo = cuerpo_de(resultado)
        estado = (resultado or {}).get("statusCode")
        if nombre == "01-abrir-turno" and estado == 201:
            p.capturado["REEMPLAZAR_TURNO_ID"] = cuerpo["turno_id"]
        if nombre == "01-consulta-cocina" and estado == 200 and cuerpo.get("jobToken"):
            p.capturado["REEMPLAZAR_TRABAJO_ID"] = cuerpo["jobToken"]
        detalle = "" if estado == esperado else f" → HTTP {estado}: {json.dumps(cuerpo, ensure_ascii=False)[:250]}"
        p.resultado(estado == esperado, f"{funcion}/{nombre} [{esperado}]{detalle}")


def asincrono(p: Prueba, cuenta: str) -> None:
    print("\n2. Procesos asíncronos reales")
    if "REEMPLAZAR_TURNO_ID" not in p.capturado:
        p.resultado(False, "no hay turno de esta ejecución: se omiten las comprobaciones asíncronas")
        return
    limite = time.monotonic() + 120
    documento = {}
    while time.monotonic() < limite:
        resultado, _ = invocar("caja", p.evento("caja", "06-documento"))
        documento = cuerpo_de(resultado) if resultado else {}
        if isinstance(documento, dict) and documento.get("estado") not in (None, "pendiente", "enviando"):
            break
        time.sleep(5)
    p.resultado(documento.get("estado") == "emitido",
                f"documento tributario: {documento.get('estado')} (folio {documento.get('folio')})")
    limite = time.monotonic() + 120
    resumen = {}
    while time.monotonic() < limite:
        resultado, _ = invocar("reportes", p.evento("reportes", "02-turno"))
        resumen = (cuerpo_de(resultado) or {}).get("resumen", {}) if resultado else {}
        if resumen.get("n_ventas"):
            break
        time.sleep(5)
    p.resultado(bool(resumen.get("n_ventas")), f"reporte del turno: {resumen.get('n_ventas', 0)} venta(s) en los agregados")
    try:
        objetos = aws("s3", "ls", f"s3://pos-archivo-{cuenta}/eventos/", "--recursive").strip().splitlines()
        p.resultado(len(objetos) > 0, f"archivo histórico: {len(objetos)} objetos en s3://pos-archivo-{cuenta}/eventos/")
    except RuntimeError as error:
        p.resultado(False, f"archivo histórico: {error}")


def mensajeria(p: Prueba) -> None:
    print("\n3. Mensajería: destinos, reglas de distribución y mensajes fallidos")
    base = "/locales/{local_id}/mensajeria"

    def llamar(ruta: str, parametros: dict | None = None, cuerpo: dict | None = None):
        escritura = not ruta.startswith("GET")
        evento = generador.http(ruta, {"local_id": generador.LOCAL, **(parametros or {})}, cuerpo, sub="mock-dueno",
                                command_id=ulid() if escritura else None)
        resultado, error = invocar("mensajeria", evento)
        if error:
            return None, {"error": error}
        return (resultado or {}).get("statusCode"), cuerpo_de(resultado)

    estado, catalogo = llamar(f"GET {base}/canales")
    if estado != 200:
        p.resultado(False, f"catálogo central → {estado}: {json.dumps(catalogo, ensure_ascii=False)[:300]}")
        return
    p.resultado(True, f"catálogo central: {len(catalogo['canales'])} canales, {len(catalogo['rutas'])} rutas, "
                      f"{len(catalogo['avisos'])} avisos")
    estado, cuerpo = llamar(f"POST {base}/destinos", cuerpo={"nombre": "", "tipo": "cola", "avisos": []})
    p.resultado(estado == 422, f"solicitud inválida rechazada [{estado}] {cuerpo.get('codigo')}: {cuerpo.get('mensaje')}")

    creados = []
    try:
        for letra, aviso in (("A", "documento_rechazado"), ("B", "comanda_en_conflicto")):
            estado, cuerpo = llamar(f"POST {base}/destinos", cuerpo={
                "nombre": f"Prueba nube {letra} {p.sufijo}", "tipo": "cola", "avisos": [aviso]})
            if estado != 201:
                p.resultado(False, f"crear destino {letra} → {estado}: {json.dumps(cuerpo, ensure_ascii=False)[:300]}")
                return
            creados.append(cuerpo)
        p.resultado(True, f"2 destinos de tipo cola creados ({creados[0]['cola']}, {creados[1]['cola']})")
        a, b = creados
        estado, prueba = llamar(f"POST {base}/pruebas", cuerpo={"aviso": "documento_rechazado"})
        esperados = [d["destino_id"] for d in (prueba or {}).get("destinos_esperados", [])]
        p.resultado(estado == 200 and esperados == [a["destino_id"]],
                    f"aviso de prueba «documento_rechazado»: la regla elige solo a {a['nombre']}")
        limite, llegados = time.monotonic() + 30, []
        while time.monotonic() < limite and not llegados:
            llegados = llamar(f"GET {base}/destinos/{{destino_id}}/mensajes", {"destino_id": a["destino_id"]})[1].get("mensajes", [])
            if not llegados:
                time.sleep(3)
        en_b = llamar(f"GET {base}/destinos/{{destino_id}}/mensajes", {"destino_id": b["destino_id"]})[1].get("mensajes", [])
        p.resultado(len(llegados) == 1 and not en_b, f"el aviso llegó a {a['nombre']} ({len(llegados)}) y no a {b['nombre']} ({len(en_b)})")
        estado, _ = llamar(f"POST {base}/destinos/{{destino_id}}/reglas", {"destino_id": a["destino_id"]}, {"aviso": "comanda_en_conflicto"})
        estado2, _ = llamar(f"DELETE {base}/destinos/{{destino_id}}/reglas/{{aviso}}",
                            {"destino_id": a["destino_id"], "aviso": "comanda_en_conflicto"})
        p.resultado((estado, estado2) == (201, 200), f"crear y eliminar una regla [{estado}, {estado2}]")
        estado, fallidos = llamar(f"GET {base}/fallidos")
        p.resultado(estado == 200, f"panel de fallidos: {len((fallidos or {}).get('fallidos', []))} apartados, "
                                   f"{len((fallidos or {}).get('errores_recientes', []))} errores recientes")
    finally:
        for destino in creados:
            estado, _ = llamar(f"DELETE {base}/destinos/{{destino_id}}", {"destino_id": destino["destino_id"]})
            p.resultado(estado == 200, f"destino {destino['nombre']} eliminado (suscripción y cola) [{estado}]")


def api(p: Prueba, url: str) -> None:
    print(f"\n3. API pública: {url}")

    def estado(ruta: str) -> int:
        try:
            with urllib.request.urlopen(url + ruta, timeout=15) as r:
                return r.status
        except urllib.error.HTTPError as error:
            return error.code
        except urllib.error.URLError as error:
            print(f"    no responde: {error.reason}")
            return 0

    p.resultado(estado("/salud") == 200, "GET /salud → 200")
    p.resultado(estado("/yo") == 401, "GET /yo sin token → 401 (autorizador activo, rutas privadas cerradas)")
    basic = "Basic " + base64.b64encode(b"imp_caja:mock-clave-caja").decode()
    url_impresora = f"{url}/impresion/demo/local_01/imp_caja"
    destino = RAIZ / "impresiones" / "imp_caja"
    try:
        imprimio = simulador_impresora.ciclo(types.SimpleNamespace(fallar=None), basic, url_impresora, destino)
    except SystemExit:  # el simulador termina si la clave es rechazada
        imprimio = False
    p.resultado(imprimio, "la impresora de caja retiró la boleta por CloudPRNT (se ve arriba)"
                if imprimio else "la impresora de caja no tenía trabajos (¿se emitió el documento?)")


def valores() -> dict[str, str]:
    archivo = RAIZ / "valores-despliegue.env"
    if not archivo.exists():
        return {}
    datos = {}
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        if "=" in linea:
            clave, valor = linea.split("=", 1)
            datos[clave] = valor.strip().strip('"')
    return datos


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba el despliegue real (sin Google)")
    parser.add_argument("--api", help="URL del API (por defecto, la de valores-despliegue.env)")
    parser.add_argument("--sin-api", action="store_true", help="omite las pruebas por HTTP")
    args = parser.parse_args()
    datos = valores()
    cuenta = datos.get("CUENTA") or aws("sts", "get-caller-identity", "--query", "Account", "--output", "text").strip()
    url = (args.api or datos.get("URL_API", "")).rstrip("/")
    p = Prueba()
    flujo(p)
    asincrono(p, cuenta)
    mensajeria(p)
    if not args.sin_api and url:
        api(p, url)
    print(f"\n{'TODO EN ORDEN' if p.fallas == 0 else f'{p.fallas} COMPROBACIONES FALLARON'}")
    return 0 if p.fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
