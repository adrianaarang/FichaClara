# tests/test_api.py
import tempfile
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from src.api import routes
from src.api.main import app
from src.api.routes import get_rag_chain
from src.common.schemas import QueryRequest, QueryResponse

client = TestClient(app)

GUIA = (
    "# Guía de administración de insulina\n\n"
    "## Conservación\n\nLos plumas sin abrir se conservan en nevera entre 2 y 8 grados.\n\n"
    "## Administración\n\nLa inyección subcutánea se rota entre abdomen, muslos y brazos.\n"
)


def _subir(nombre: str, contenido: bytes, tipo: str = "text/markdown"):
    return client.post("/ingest", files={"file": (nombre, contenido, tipo)})


def _pdf(paginas: int = 2) -> bytes:
    doc = pymupdf.open()
    for n in range(paginas):
        pagina = doc.new_page()
        texto = f"Pagina {n + 1}. " + "Este es un documento interno de prueba sobre cuidados. " * 6
        pagina.insert_textbox(pymupdf.Rect(50, 50, 550, 750), texto)
    return doc.tobytes()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200


# ---------------------------------------------------------------- /query

def test_query_devuelve_lo_que_responde_la_cadena():
    class CadenaFalsa:
        def answer(self, request: QueryRequest) -> QueryResponse:
            return QueryResponse(respuesta=f"eco: {request.pregunta}", encontrado=False)

    app.dependency_overrides[get_rag_chain] = CadenaFalsa
    try:
        response = client.post("/query", json={"pregunta": "¿Para qué sirve el Januvia?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["respuesta"] == "eco: ¿Para qué sirve el Januvia?"


# ---------------------------------------------------------------- /ingest

def test_ingest_procesa_con_p1_e_indexa_con_p2():
    with (
        patch.object(routes, "delete_document", return_value=0) as borrar,
        patch.object(routes, "add_chunks") as indexar,
    ):
        response = _subir("guia_insulina.md", GUIA.encode())

    assert response.status_code == 200
    cuerpo = response.json()
    chunks_indexados = indexar.call_args.args[0]
    assert cuerpo["chunks"] == len(chunks_indexados) > 0
    assert cuerpo["tipo_documento"] == "documento"
    assert cuerpo["nombre"] == "guia_insulina.md"
    assert cuerpo["paginas"] == 1
    assert cuerpo["ya_existia"] is False
    assert cuerpo["doc_id"].startswith("guia-insulina-")  # P1: nombre normalizado + huella del contenido
    assert {c.metadata.doc_id for c in chunks_indexados} == {cuerpo["doc_id"]}
    borrar.assert_called_once_with(cuerpo["doc_id"])


def test_ingest_de_un_documento_ya_indexado_lo_reemplaza():
    with (
        patch.object(routes, "delete_document", return_value=4),
        patch.object(routes, "add_chunks"),
    ):
        response = _subir("guia_insulina.md", GUIA.encode())

    assert response.status_code == 200
    assert response.json()["ya_existia"] is True


def test_ingest_pdf_cuenta_las_paginas():
    with (
        patch.object(routes, "delete_document", return_value=0),
        patch.object(routes, "add_chunks"),
    ):
        response = _subir("cuidados.pdf", _pdf(paginas=2), "application/pdf")

    assert response.status_code == 200
    assert response.json()["paginas"] == 2


def test_ingest_acepta_la_ruta_completa_de_windows_como_nombre():
    with (
        patch.object(routes, "delete_document", return_value=0),
        patch.object(routes, "add_chunks"),
    ):
        response = _subir(r"C:\Users\ana\Documents\guia_insulina.md", GUIA.encode())

    assert response.status_code == 200
    assert response.json()["nombre"] == "guia_insulina.md"


@pytest.mark.parametrize(
    "nombre, contenido, codigo",
    [
        ("programa.exe", b"MZ....", 415),
        ("vacio.txt", b"", 422),
        ("escaneo.pdf", b"esto no es un pdf", 422),
    ],
)
def test_ingest_rechaza_documentos_que_no_se_pueden_leer(nombre, contenido, codigo):
    with (
        patch.object(routes, "delete_document") as borrar,
        patch.object(routes, "add_chunks") as indexar,
    ):
        response = _subir(nombre, contenido)

    assert response.status_code == codigo
    assert response.json()["detail"]
    borrar.assert_not_called()  # un fallo al leer no toca el índice
    indexar.assert_not_called()


def test_un_fallo_al_limpiar_el_temporal_no_tapa_el_error_real(tmp_path, monkeypatch):
    """En Windows, PyMuPDF puede dejar bloqueado un PDF que no ha podido abrir y borrar la carpeta
    temporal falla (WinError 32). Eso no debe convertir un 422 (documento ilegible) en un 500."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))  # los restos del test quedan en tmp_path
    with (
        patch("os.unlink", side_effect=PermissionError("archivo en uso")),
        patch.object(routes, "delete_document"),
        patch.object(routes, "add_chunks"),
    ):
        response = _subir("escaneo.pdf", b"esto no es un pdf")

    assert response.status_code == 422


def test_ingest_sin_archivo_es_un_error_de_validacion():
    assert client.post("/ingest", json={"doc_id": "x"}).status_code == 422


def test_ingest_rechaza_archivos_demasiado_grandes(monkeypatch):
    monkeypatch.setattr(routes, "MAX_BYTES_SUBIDA", 10)
    assert _subir("grande.txt", b"x" * 11).status_code == 413


# ---------------------------------------------------------------- /documents

def test_get_documents_lista_lo_indexado():
    indexados = [
        {"doc_id": "FT_83208", "nombre": "ANTIDOL INFANTIL", "tipo_documento": "ficha_tecnica", "chunks": 40},
        {"doc_id": "guia-1a2b3c4d", "nombre": "guia.md", "tipo_documento": "documento", "chunks": 3},
    ]
    with patch.object(routes, "list_documents", return_value=indexados):
        response = client.get("/documents")

    assert response.status_code == 200
    assert response.json() == indexados


def test_get_documents_vacio():
    with patch.object(routes, "list_documents", return_value=[]):
        assert client.get("/documents").json() == []


def test_delete_document_borra_de_chroma():
    with patch.object(routes, "delete_document", return_value=3) as borrar:
        response = client.delete("/documents/guia-1a2b3c4d")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "document_id": "guia-1a2b3c4d", "chunks_eliminados": 3}
    borrar.assert_called_once_with("guia-1a2b3c4d")


def test_delete_document_inexistente_da_404():
    with patch.object(routes, "delete_document", return_value=0):
        assert client.delete("/documents/no-existe").status_code == 404
