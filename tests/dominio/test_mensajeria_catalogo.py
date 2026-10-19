"""Catálogo central de mensajería: coherencia interna, validación de solicitudes y consistencia con la
documentación (02) y con el despliegue (desplegar.sh lee las colas del catálogo)."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from pos_dominio import efectos, mensajeria as M
from pos_dominio.errores import Validacion

RAIZ = Path(__file__).parents[2]
DOC_API = RAIZ / "docs" / "migracion" / "02-api-gateway.md"


# --- coherencia interna -----------------------------------------------------------------------------------

def test_rutas_avisos_y_fallidos_apuntan_a_canales_existentes():
    for ruta in M.RUTAS:
        assert ruta.canal in M.CANALES, ruta
    for aviso in M.AVISOS.values():
        assert M.CANALES[aviso.canal].tipo == "tema", aviso
        assert M.CANALES[aviso.canal].variable, aviso
    for canal in M.CANALES.values():
        if canal.fallidos:
            fallidos = M.CANALES[canal.fallidos]
            assert fallidos.tipo == "cola_fallidos" and fallidos.fifo == canal.fifo, canal
        if canal.tipo == "cola":
            assert canal.fallidos and canal.max_recepciones and canal.variable, canal
    for canal_id in M.COLAS_CON_REPROCESO:
        assert M.CANALES[canal_id].tipo == "cola"


def test_todo_aviso_que_publica_el_codigo_esta_en_el_catalogo():
    fuentes = (RAIZ / "lambdas" / "capa" / "python" / "pos_dominio" / "efectos.py").read_text(encoding="utf-8")
    fuentes += (RAIZ / "lambdas" / "funciones" / "tareas-programadas" / "lambda_function.py").read_text(encoding="utf-8")
    publicados = set(re.findall(r'return \[\("([a-z_]+)", "MISE', fuentes)) | set(re.findall(r'publicar_aviso\("([a-z_]+)"', fuentes))
    assert publicados == set(M.AVISOS), publicados ^ set(M.AVISOS)


def test_avisos_de_un_evento_salen_con_su_id_del_catalogo():
    evento = {"tipo": "dte.rechazado", "tenant_id": "demo", "local_id": "local_01",
              "datos": {"venta_id": "v1", "motivo": "RUT"}}
    [(aviso, asunto, _)] = efectos.avisos(evento)
    assert aviso == "documento_rechazado" and M.canal_de_aviso(aviso).id == "avisos" and "rechazado" in asunto


# --- reglas de distribución -----------------------------------------------------------------------------

def test_la_regla_filtra_por_aviso_y_por_local():
    politica = M.politica_de_filtro("demo", "local_01", ["documento_rechazado"])
    assert M.recibe(politica, M.atributos_aviso("documento_rechazado", "demo", "local_01"))
    assert M.recibe(politica, M.atributos_aviso("documento_rechazado", "demo", "local_01", prueba=True))
    assert not M.recibe(politica, M.atributos_aviso("comanda_en_conflicto", "demo", "local_01"))
    assert not M.recibe(politica, M.atributos_aviso("documento_rechazado", "demo", "local_02"))
    assert not M.recibe(politica, M.atributos_aviso("documento_rechazado", "otro", "local_01"))


# --- validación de solicitudes -----------------------------------------------------------------------------

def test_destino_valido_se_normaliza():
    datos = M.validar_destino({"nombre": "  Jefe   de turno ", "tipo": "correo", "correo": " Jefe@Demo.CL ",
                               "avisos": ["documento_rechazado", "comanda_en_conflicto"]})
    assert datos == {"nombre": "Jefe de turno", "tipo": "correo", "correo": "jefe@demo.cl",
                     "avisos": ["documento_rechazado", "comanda_en_conflicto"]}
    assert M.validar_destino({"nombre": "Contabilidad", "tipo": "cola", "avisos": ["cierre_con_diferencia"]})["tipo"] == "cola"


@pytest.mark.parametrize("cuerpo, codigo, campo", [
    ("texto", "CAMPO_INVALIDO", "cuerpo"),
    ({"nombre": "", "tipo": "cola", "avisos": ["documento_rechazado"]}, "NOMBRE_INVALIDO", "nombre"),
    ({"nombre": "x" * 61, "tipo": "cola", "avisos": ["documento_rechazado"]}, "NOMBRE_INVALIDO", "nombre"),
    ({"nombre": "<script>", "tipo": "cola", "avisos": ["documento_rechazado"]}, "NOMBRE_INVALIDO", "nombre"),
    ({"nombre": "A", "tipo": "sms", "avisos": ["documento_rechazado"]}, "TIPO_DESTINO_INVALIDO", "tipo"),
    ({"nombre": "A", "tipo": "correo", "correo": "no-es-correo", "avisos": ["documento_rechazado"]}, "CORREO_INVALIDO", "correo"),
    ({"nombre": "A", "tipo": "correo", "avisos": ["documento_rechazado"]}, "CORREO_INVALIDO", "correo"),
    ({"nombre": "A", "tipo": "cola", "correo": "a@b.cl", "avisos": ["documento_rechazado"]}, "CAMPO_NO_CORRESPONDE", "correo"),
    ({"nombre": "A", "tipo": "cola", "avisos": []}, "REGLAS_REQUERIDAS", "avisos"),
    ({"nombre": "A", "tipo": "cola", "avisos": "documento_rechazado"}, "REGLAS_REQUERIDAS", "avisos"),
    ({"nombre": "A", "tipo": "cola", "avisos": ["no_existe"]}, "AVISO_DESCONOCIDO", "avisos[0]"),
    ({"nombre": "A", "tipo": "cola", "avisos": ["documento_fallido"]}, "AVISO_NO_ADMINISTRABLE", "avisos[0]"),
    ({"nombre": "A", "tipo": "cola", "avisos": ["documento_rechazado", "documento_rechazado"]}, "REGLA_REPETIDA", "avisos[1]"),
    ({"nombre": "A", "tipo": "cola", "avisos": ["documento_rechazado"], "cola": "x"}, "CAMPO_DESCONOCIDO", "cola"),
])
def test_destino_invalido_se_rechaza_con_campo_y_codigo(cuerpo, codigo, campo):
    with pytest.raises(Validacion) as error:
        M.validar_destino(cuerpo)
    assert (error.value.codigo, error.value.detalle["campo"], error.value.http) == (codigo, campo, 422)


def test_canal_de_reproceso_y_destino_id():
    assert M.validar_canal_reproceso("dte-emision") == "dte-emision"
    for malo in ("avisos", "dte-emision-fallidos", None):
        with pytest.raises(Validacion):
            M.validar_canal_reproceso(malo)
    with pytest.raises(Validacion):
        M.validar_destino_id("../otro")


def test_nombre_de_la_cola_de_un_destino_es_valido_en_sqs():
    nombre = M.nombre_cola_destino("01K7H0Z3Q8W4M2N5P6R7S8T9VA")
    assert re.fullmatch(r"[a-z0-9_\-]{1,80}", nombre)


# --- consistencia con la documentación y el despliegue ---------------------------------------------------

def test_la_tabla_de_colas_de_02_coincide_con_el_catalogo():
    texto = DOC_API.read_text(encoding="utf-8")
    tabla = texto[texto.index("## 9. Colas"):]
    for canal in M.CANALES.values():
        if canal.tipo not in ("cola", "cola_fallidos"):
            continue
        fila = next((l for l in tabla.splitlines() if l.startswith(f"| `{canal.nombre_aws}` |")), None)
        assert fila, f"{canal.nombre_aws} no está en la tabla de colas de 02"
        assert f"{canal.visibilidad} s" in fila, fila
        assert ("FIFO" in fila.split("|")[2]) == canal.fifo, fila
        if canal.fallidos:
            assert f"`{M.CANALES[canal.fallidos].nombre_aws}`" in fila and f"{canal.max_recepciones} recepciones" in fila


def test_el_despliegue_crea_las_colas_desde_el_catalogo():
    script = (RAIZ / "infra" / "cloudshell" / "desplegar.sh").read_text(encoding="utf-8")
    assert "done < <($AY canales)" in script
    for canal in M.CANALES.values():
        if canal.tipo in ("cola", "cola_fallidos"):
            # Se permite el id del catálogo como clave (${URL_COLA[dte-emision]}), no el nombre escrito a mano.
            sueltos = re.findall(rf"(?<![\[\w-]){re.escape(canal.nombre_aws)}(?![\w\].-])", script)
            assert not sueltos, f"{canal.nombre_aws} está escrito a mano en desplegar.sh"
    salida = subprocess.run([sys.executable, str(RAIZ / "infra" / "cloudshell" / "ayudante.py"), "canales"],
                            capture_output=True, text=True, check=True).stdout.split("\n")
    filas = [l.rstrip("\r").split("\t") for l in salida if l.strip()]
    vistos = set()
    for id_, nombre, fifo, visibilidad, recepciones, fallidos in filas:
        if fallidos != "-":
            assert fallidos in vistos, "la cola de fallidos debe crearse antes que la cola que la usa"
        vistos.add(id_)
        canal = M.CANALES[id_]
        assert (nombre, fifo == "si", int(visibilidad)) == (canal.nombre_aws, canal.fifo, canal.visibilidad)


def test_las_variables_de_los_canales_son_las_que_usan_las_funciones():
    funciones = RAIZ / "lambdas" / "funciones"
    codigo = "".join(p.read_text(encoding="utf-8") for p in funciones.glob("*/lambda_function.py"))
    for canal in M.CANALES.values():
        if canal.variable:
            assert canal.variable in codigo, canal.variable
