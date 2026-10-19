"""scripts/validar_despliegue.py --simulado recorre el flujo completo sin AWS ni Google."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

import validar_despliegue  # noqa: E402


def test_validacion_simulada_completa(capsys):
    entorno = dict(os.environ)
    try:
        assert validar_despliegue.main(["--simulado"]) == 0
    finally:
        os.environ.clear()
        os.environ.update(entorno)
        from pos_dominio.infra import aws, identidad
        aws.reiniciar()
        identidad.limpiar_cache()
    salida = capsys.readouterr().out
    assert "VALIDACIÓN COMPLETA: 13/13 pasos" in salida


def test_rechaza_un_token_que_no_es_jwt():
    t = validar_despliegue.TransporteHttp("https://ejemplo", "no-es-un-jwt", espera_maxima=1)
    args = type("A", (), {"local": "local_01", "emisor": "https://accounts.google.com"})()
    v = validar_despliegue.Validacion(t, args)
    try:
        v.revisar_token()
    except validar_despliegue.Fallo as error:
        assert "no es un JWT" in str(error)
    else:
        raise AssertionError("debió fallar")
