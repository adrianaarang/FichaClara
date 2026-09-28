"""Tests del chunker.

Responsable: Adriana (P1)
"""
from pathlib import Path

from src.ingestion.chunker import (
    MAX_SECCION,
    es_titulo_de_seccion,
    extraer_fecha,
    trocear_documento,
)
from src.ingestion.cleaner import limpiar_documento
from src.ingestion.loaders import DocumentoCargado, Pagina, cargar_documento

FIXTURES = Path(__file__).parent / "fixtures"
INFO = {"nombre": "Acfol 5 mg comprimidos", "principios_activos": "ACIDO FOLICO", "atc": "B03BB01"}


def ficha_sintetica(paginas: list[str]) -> DocumentoCargado:
    return DocumentoCargado(doc_id="FT_999", ruta=Path("FT_999.pdf"), formato="pdf", es_ficha_tecnica=True,
                            origen="aemps", nregistro="999",
                            paginas=[Pagina(i, t) for i, t in enumerate(paginas, start=1)])


TODAS = "\n".join(f"{n}. {t}\nContenido de {n}." for n, t in [
    ("1", "NOMBRE DEL MEDICAMENTO"), ("2", "COMPOSICIÓN"), ("3", "FORMA FARMACÉUTICA"), ("4", "DATOS CLÍNICOS"),
    ("4.1", "Indicaciones terapéuticas"), ("4.2", "Posología y forma de administración"),
    ("4.3", "Contraindicaciones"), ("4.5", "Interacción con otros medicamentos"), ("4.8", "Reacciones adversas"),
    ("10", "FECHA DE LA REVISIÓN DEL TEXTO")])


# ---------------------------------------------------------------- ficha real

def test_ficha_real_por_secciones():
    doc = limpiar_documento(cargar_documento(FIXTURES / "FT_11265.pdf"))
    chunks = trocear_documento(doc, INFO)
    secciones = {c.metadata.seccion for c in chunks}
    assert {"4.1", "4.2", "4.3", "4.5", "4.8", "6.1", "10"} <= secciones
    assert len({c.metadata.chunk_id for c in chunks}) == len(chunks)  # ids únicos
    c45 = next(c for c in chunks if c.metadata.seccion == "4.5")
    assert c45.texto.startswith("[Acfol 5 mg comprimidos · 4.5 Interacción")
    assert "fenobarbital" in c45.texto
    assert c45.metadata.pagina_inicio == 2 and c45.metadata.atc == "B03BB01"
    assert c45.metadata.url_fuente == "https://cima.aemps.es/cima/dochtml/ft/11265/4.5/FichaTecnica.html"
    assert c45.metadata.fecha_revision == "Diciembre 2020"
    assert all(c.metadata.tipo_documento == "ficha_tecnica" for c in chunks)


# ---------------------------------------------------------------- detección de títulos

def test_titulos_solo_de_la_plantilla_y_en_orden():
    texto = TODAS.replace("Contenido de 4.2.", "Ver apartado:\n4.3. Contraindicaciones del grupo") \
        + "\n1. Poner la cantidad de agua"
    chunks = trocear_documento(ficha_sintetica([texto]))
    numeros = [c.metadata.seccion for c in chunks]
    assert numeros.count("4.3") == 1          # el segundo "4.3." dentro de 4.2 no abre sección nueva
    assert numeros.count("1") == 1            # la lista "1. Poner…" no es la sección 1


def test_encaje_del_titulo():
    assert es_titulo_de_seccion("4.5", "Interacción con otros medicamentos y otras formas de interacción")
    assert not es_titulo_de_seccion("4.5", "mg dos veces al día")
    assert not es_titulo_de_seccion("4.2.1", "Posología")


def test_pocas_secciones_usa_troceo_generico():
    chunks = trocear_documento(ficha_sintetica(["1. NOMBRE DEL MEDICAMENTO\nX\n4.2. Posología\nY"]))
    assert chunks[0].metadata.tipo_documento == "documento" and chunks[0].metadata.seccion is None


# ---------------------------------------------------------------- tamaños y páginas

def test_seccion_larga_se_divide_sin_mezclar_secciones():
    larga = " ".join(f"Frase número {i} sobre interacciones." for i in range(200))
    texto = TODAS.replace("Contenido de 4.5.", larga)
    chunks = trocear_documento(ficha_sintetica([texto]))
    partes = [c for c in chunks if c.metadata.seccion == "4.5"]
    assert len(partes) > 1
    assert all(c.metadata.total_partes == len(partes) for c in partes)
    assert all("Contenido de 4.8" not in c.texto for c in partes)   # el solape no cruza a 4.8
    assert "parte 2/" in partes[1].texto.splitlines()[0]
    assert all(len(c.texto.split("\n", 1)[1]) <= MAX_SECCION for c in partes)


def test_paginas_de_una_seccion_que_cruza_de_pagina():
    p1 = TODAS.split("4.8.")[0] + "4.8. Reacciones adversas\nCefalea frecuente."
    chunks = trocear_documento(ficha_sintetica([p1, "Mareo raro.\n10. FECHA DE LA REVISIÓN DEL TEXTO\nJulio 2024"]))
    c48 = next(c for c in chunks if c.metadata.seccion == "4.8")
    assert (c48.metadata.pagina_inicio, c48.metadata.pagina_fin) == (1, 2)
    assert c48.metadata.fecha_revision == "Julio 2024"


# ---------------------------------------------------------------- documentos genéricos

def test_markdown_por_titulos():
    doc = DocumentoCargado(doc_id="guia-1", ruta=Path("guia.md"), formato="md", es_ficha_tecnica=False,
                           origen=None, nregistro=None,
                           paginas=[Pagina(1, "# Disfagia\nTriturar solo si la ficha lo permite.\n# Sondas\nLavar.")])
    chunks = trocear_documento(doc)
    assert [c.metadata.titulo_seccion for c in chunks] == ["Disfagia", "Sondas"]
    assert chunks[0].texto.startswith("[guia.md · Disfagia]")
    assert chunks[0].metadata.url_fuente is None


def test_fechas():
    assert extraer_fecha("Julio 2024") == "Julio 2024"
    assert extraer_fecha("03/2023") == "03/2023"
    assert extraer_fecha("<{MM/AAAA}>") is None


def test_ficha_ema_con_varias_presentaciones():
    # Caso real (Aerius): el Anexo I trae la ficha de comprimidos (1..10) y luego la de solución oral (1..10)
    bloque = TODAS.replace("Contenido de 1.", "{nombre}").replace("Contenido de 10.", "{fecha}")
    texto = bloque.format(nombre="Aerius 5 mg comprimidos", fecha="Enero 2024") + "\n" + \
        bloque.format(nombre="Aerius 0,5 mg/ml solución oral", fecha="Mayo 2025")
    chunks = trocear_documento(ficha_sintetica([texto]))
    c48 = [c for c in chunks if c.metadata.seccion == "4.8"]
    assert len(c48) == 2
    assert c48[0].texto.startswith("[Aerius 5 mg comprimidos · 4.8")
    assert c48[1].texto.startswith("[Aerius 0,5 mg/ml solución oral · 4.8")
    assert c48[1].metadata.chunk_id == "FT_999::p2::4.8::1"
    assert c48[1].metadata.fecha_revision == "Mayo 2025"
    assert "Contenido de 4.8" not in next(c.texto for c in chunks if c.metadata.seccion == "10")
    assert len({c.metadata.chunk_id for c in chunks}) == len(chunks)


def test_una_frecuencia_no_es_una_fecha():
    assert extraer_fecha("raras (≥1/10.000 a < 1/1.000)") is None
    assert extraer_fecha("19.03.2008") == "19.03.2008"
