"""Tests del experimento de chunking (fijo 500/1.000 frente a por sección).

Responsable: P1 · Ingesta y chunking
"""
from pathlib import Path

from src.ingestion.cleaner import limpiar_documento
from src.ingestion.experimento_chunking import evaluar_documento, resumir
from src.ingestion.loaders import cargar_documento

FICHA = Path("tests/fixtures/FT_11265.pdf")


def _doc():
    return limpiar_documento(cargar_documento(FICHA))


def test_por_seccion_nunca_mezcla_secciones():
    resultado = evaluar_documento(_doc())
    r = resumir("por_seccion", [resultado["por_seccion"]])
    assert r.pct_mezcla == 0.0


def test_troceo_fijo_mezcla_mas_que_por_seccion():
    resultado = evaluar_documento(_doc())
    fijo_500 = resumir("fijo_500", [resultado["fijo_500"]])
    por_seccion = resumir("por_seccion", [resultado["por_seccion"]])
    assert fijo_500.pct_mezcla > por_seccion.pct_mezcla


def test_por_seccion_mantiene_mas_secciones_clave_enteras():
    resultado = evaluar_documento(_doc())
    fijo_500 = resumir("fijo_500", [resultado["fijo_500"]])
    por_seccion = resumir("por_seccion", [resultado["por_seccion"]])
    assert por_seccion.pct_clave_entera >= fijo_500.pct_clave_entera
