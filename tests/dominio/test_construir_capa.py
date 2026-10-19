"""El .zip de la capa tiene la estructura que exige Lambda y se puede importar desde él."""

import importlib.util
import os
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))

import construir_capa  # noqa: E402


def test_zip_con_carpeta_python_en_la_raiz(tmp_path):
    destino = construir_capa.construir(tmp_path / "capa.zip")
    with zipfile.ZipFile(destino) as zip_capa:
        nombres = zip_capa.namelist()
    assert "python/pos_dominio/__init__.py" in nombres
    assert "python/pos_dominio/datos/America_Santiago" in nombres
    assert all(n.startswith("python/pos_dominio/") for n in nombres)
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in nombres)


def test_el_zip_es_reproducible(tmp_path):
    a = construir_capa.construir(tmp_path / "a.zip").read_bytes()
    b = construir_capa.construir(tmp_path / "b.zip").read_bytes()
    assert a == b


def test_se_importa_desde_el_zip_como_lo_haria_lambda(tmp_path):
    # Lambda descomprime la capa en /opt y agrega /opt/python al path.
    destino = construir_capa.construir(tmp_path / "capa.zip")
    opt = tmp_path / "opt"
    with zipfile.ZipFile(destino) as zip_capa:
        zip_capa.extractall(opt)
    codigo = ("import pos_dominio.operaciones.caja, pos_dominio.infra.dynamodb, pos_dominio.tiempo as t;"
              "print(t.fecha_operativa(t.desde_iso('2026-10-14T02:30:00.000Z')))")
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                            env={"PYTHONPATH": str(opt / "python"), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
                            check=True)
    assert salida.stdout.strip() == "2026-10-13"
    assert importlib.util.find_spec("pos_dominio") is not None
