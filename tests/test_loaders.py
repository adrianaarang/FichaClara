"""Tests de carga de documentos.

Usa una ficha técnica real pequeña (tests/fixtures/FT_11265.pdf, Acfol 5 mg, AEMPS)
y PDFs sintéticos generados al vuelo.

Responsable: P1
"""
from pathlib import Path

import pymupdf
import pytest

from src.ingestion.loaders import (
    DocumentoIlegibleError,
    FormatoNoSoportadoError,
    Pagina,
    cargar_documento,
    detectar_ficha_tecnica,
    recortar_anexos_ema,
    tabla_a_texto,
)

FIXTURES = Path(__file__).parent / "fixtures"


def crear_pdf(ruta: Path, textos: list[str]) -> Path:
    doc = pymupdf.open()
    for t in textos:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), t, fontsize=10)
    doc.save(ruta)
    return ruta


# ---------------------------------------------------------------- ficha real

def test_ficha_real_aemps():
    doc = cargar_documento(FIXTURES / "FT_11265.pdf")
    assert doc.doc_id == "FT_11265" and doc.nregistro == "11265"
    assert doc.origen == "aemps" and doc.es_ficha_tecnica
    assert [p.numero for p in doc.paginas] == [1, 2, 3, 4, 5]
    assert "4.5. Interacción con otros medicamentos" in doc.texto_completo
    assert "fenitoina" in doc.texto_completo


# ---------------------------------------------------------------- errores

def test_formato_no_soportado(tmp_path: Path):
    f = tmp_path / "hoja.xlsx"
    f.write_bytes(b"x")
    with pytest.raises(FormatoNoSoportadoError):
        cargar_documento(f)


def test_pdf_vacio_o_corrupto(tmp_path: Path):
    vacio = tmp_path / "vacio.pdf"
    vacio.write_bytes(b"")
    corrupto = tmp_path / "corrupto.pdf"
    corrupto.write_bytes(b"esto no es un pdf")
    for f in (vacio, corrupto):
        with pytest.raises(DocumentoIlegibleError):
            cargar_documento(f)


def test_pdf_escaneado_sin_texto(tmp_path: Path):
    f = crear_pdf(tmp_path / "escaneo.pdf", ["", ""])
    with pytest.raises(DocumentoIlegibleError, match="escaneo"):
        cargar_documento(f)


# ---------------------------------------------------------------- TXT / MD / PDF genérico

def test_txt_en_cp1252(tmp_path: Path):
    f = tmp_path / "guía interna.txt"
    f.write_bytes("Protocolo de administración de fármacos por sonda".encode("cp1252"))
    doc = cargar_documento(f)
    assert doc.formato == "txt" and not doc.es_ficha_tecnica
    assert "administración" in doc.texto_completo
    assert doc.doc_id.startswith("guia-interna-")


def test_md_y_id_estable(tmp_path: Path):
    f = tmp_path / "Protocolo.md"
    f.write_text("# Disfagia\n\nTriturar solo si la ficha lo permite.", encoding="utf-8")
    a, b = cargar_documento(f), cargar_documento(f)
    assert a.formato == "md" and a.doc_id == b.doc_id and a.doc_id.startswith("protocolo-")


def test_pdf_generico_no_es_ficha(tmp_path: Path):
    f = crear_pdf(tmp_path / "guia.pdf", ["Guía de farmacia del centro. " * 20])
    doc = cargar_documento(f)
    assert doc.formato == "pdf" and doc.origen is None and doc.nregistro is None


# ---------------------------------------------------------------- fichas EMA

def test_detectar_formato():
    ema = [Pagina(1, "ANEXO I\nFICHA TÉCNICA O RESUMEN DE LAS CARACTERÍSTICAS DEL PRODUCTO")]
    aemps = [Pagina(1, "1 de 5\nFICHA TÉCNICA\n1. NOMBRE DEL MEDICAMENTO")]
    assert detectar_ficha_tecnica(ema) == "ema"
    assert detectar_ficha_tecnica(aemps) == "aemps"
    assert detectar_ficha_tecnica([Pagina(1, "Un documento cualquiera")]) is None


def test_recorta_anexos_y_portada_ema():
    paginas = [
        Pagina(1, "ANEXO I\nFICHA TÉCNICA O RESUMEN DE LAS CARACTERÍSTICAS DEL PRODUCTO"),
        Pagina(2, "1.\nNOMBRE DEL MEDICAMENTO\nEjemplo 75 mg"),
        Pagina(3, "10.\nFECHA DE LA REVISIÓN DEL TEXTO\nEnero 2025\nANEXO II\nFABRICANTE"),
        Pagina(4, "ANEXO III\nETIQUETADO Y PROSPECTO"),
    ]
    resultado = recortar_anexos_ema(paginas)
    assert [p.numero for p in resultado] == [2, 3]  # se conservan los nº de página reales
    assert "ANEXO II" not in resultado[-1].texto and "Enero 2025" in resultado[-1].texto


# ---------------------------------------------------------------- tablas

CABECERA_48 = ["Sistema de clasificación", "Muy frecuentes", "Frecuentes", "Poco frecuentes", "Raras"]


def test_tabla_de_frecuencias_se_linealiza():
    texto, cab = tabla_a_texto([CABECERA_48, ["Trastornos del sistema\nnervioso", "Cefalea", "Insomnio", None, ""]])
    assert "Trastornos del sistema nervioso — Muy frecuentes: Cefalea; Frecuentes: Insomnio" in texto
    assert cab == CABECERA_48


def test_tabla_continua_en_la_pagina_siguiente():
    _, cab = tabla_a_texto([CABECERA_48, ["Infecciones", "", "Bronquitis", "", ""]])
    texto, _ = tabla_a_texto([["Trastornos oculares", "", "", "", "Deterioro visual"]], cab)
    assert texto == "Trastornos oculares — Raras: Deterioro visual"


def test_tabla_normal_usa_primera_fila_como_cabecera():
    texto, _ = tabla_a_texto([["Peso corporal", "Dosis"], [">40 kg", "75 mg dos veces al día"]])
    assert "[Tabla] Peso corporal | Dosis" in texto
    assert ">40 kg — Dosis: 75 mg dos veces al día" in texto
