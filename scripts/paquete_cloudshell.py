"""Arma dist/pos-cloudshell.zip: todo lo que CloudShell necesita para desplegar y probar.

Uso, desde POS/POS en tu computador:
    python scripts/paquete_cloudshell.py

Luego, en CloudShell: Actions → Upload file → dist/pos-cloudshell.zip, y
    unzip -o pos-cloudshell.zip -d pos && cd pos && bash infra/cloudshell/desplegar.sh

Incluye el código de las funciones y la capa (CloudShell arma los .zip de Lambda), los scripts,
la infraestructura, los eventos de prueba, la tabla de rutas y la PWA ya compilada (pwa/dist: antes,
en tu PC, `cd pwa && npm ci && npm run build`). No incluye pruebas, .venv ni dist (salvo pwa/dist).

Si CloudShell no deja subir el .zip, usa dist/cloudshell-partes/pos-parte-01.txt, -02, ...: el mismo
.zip en base64, partido en archivos de texto pequeños. Se suben uno por uno y se rearman con
    cat pos-parte-*.txt | base64 -d > pos-cloudshell.zip
"""

from __future__ import annotations

import base64
import hashlib
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "dist" / "pos-cloudshell.zip"
PARTES = RAIZ / "dist" / "cloudshell-partes"
INCLUIR = ["lambdas", "scripts", "infra", "eventos-prueba", "docs/migracion/02-api-gateway.md", "pwa/dist"]
MAX_PARTES = 99  # dos dígitos: `cat pos-parte-*.txt` las ordena bien hasta pos-parte-99.txt
# La compilación deja aquí el config.json de desarrollo; el de la nube lo escribe publicar_pwa.sh.
_EXCLUIR = {"pwa/dist/config.json"}
_FECHA = (2026, 1, 1, 0, 0, 0)


def archivos() -> list[Path]:
    lista: list[Path] = []
    for entrada in INCLUIR:
        ruta = RAIZ / entrada
        candidatos = [ruta] if ruta.is_file() else sorted(ruta.rglob("*"))
        lista += [p for p in candidatos if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
                  and p.relative_to(RAIZ).as_posix() not in _EXCLUIR]
    return lista


def construir(destino: Path = DESTINO) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
        for archivo in archivos():
            info = zipfile.ZipInfo(archivo.relative_to(RAIZ).as_posix(), date_time=_FECHA)
            # Los .sh quedan ejecutables al descomprimir en CloudShell.
            info.external_attr = (0o755 if archivo.suffix == ".sh" else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            contenido = archivo.read_bytes()
            if archivo.suffix in (".sh", ".py", ".sql", ".md", ".json", ".html") and not info.filename.startswith("pwa/dist/"):
                # Windows guarda CRLF; bash en CloudShell falla con "\r: command not found".
                # Lo compilado (pwa/dist) no se toca: la versión del service worker depende de sus bytes.
                contenido = contenido.replace(b"\r\n", b"\n")
            paquete.writestr(info, contenido)
    return destino


def partir(zip_: Path, carpeta: Path = PARTES, lineas_por_parte: int = 800) -> list[Path]:
    """Escribe el .zip en base64 (líneas de 76 caracteres) repartido en pos-parte-01.txt, -02, ..."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for anterior in carpeta.glob("pos-parte-*.txt"):
        anterior.unlink()
    lineas = base64.encodebytes(zip_.read_bytes()).decode("ascii").splitlines()
    grupos = [lineas[i:i + lineas_por_parte] for i in range(0, len(lineas), lineas_por_parte)]
    if len(grupos) > MAX_PARTES:
        raise ValueError("demasiadas partes: sube lineas_por_parte")
    partes = []
    for numero, grupo in enumerate(grupos, start=1):
        parte = carpeta / f"pos-parte-{numero:02d}.txt"
        parte.write_bytes(("\n".join(grupo) + "\n").encode("ascii"))
        partes.append(parte)
    return partes


def main() -> int:
    destino = construir()
    with zipfile.ZipFile(destino) as paquete:
        nombres = paquete.namelist()
    if "infra/cloudshell/desplegar.sh" not in nombres:
        print("ERROR: falta infra/cloudshell/desplegar.sh", file=sys.stderr)
        return 1
    print(f"{destino.relative_to(RAIZ)}  {len(nombres)} archivos  {destino.stat().st_size // 1024} KB")
    print("Súbelo a CloudShell (Actions > Upload file) y ejecuta:")
    print("  unzip -o pos-cloudshell.zip -d pos && cd pos && bash infra/cloudshell/desplegar.sh")
    partes = partir(destino)
    print(f"\nSi no deja subir el .zip: sube uno por uno los {len(partes)} archivos de "
          f"{PARTES.relative_to(RAIZ)} y ejecuta:")
    print("  cd ~ && cat pos-parte-*.txt | base64 -d > pos-cloudshell.zip && sha256sum pos-cloudshell.zip")
    print(f"  (debe mostrar {hashlib.sha256(destino.read_bytes()).hexdigest()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
