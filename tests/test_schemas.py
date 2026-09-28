"""Tests de los contratos compartidos.

Responsable: Josema (P3, custodia) · Propuesta: Adriana (P1)
"""
import pytest
from pydantic import ValidationError

from src.common.schemas import Chunk, ChunkMetadata, QueryRequest, QueryResponse


def metadata(**cambios):
    datos = {"chunk_id": "FT_54503::4.5::1", "doc_id": "FT_54503", "tipo_documento": "ficha_tecnica",
             "nombre": "Lopresor 100 mg comprimidos", "nregistro": "54503", "seccion": "4.5",
             "titulo_seccion": "Interacción con otros medicamentos", "pagina_inicio": 4, "pagina_fin": 6,
             "orden": 12}
    datos.update(cambios)
    return ChunkMetadata(**datos)


def test_metadata_a_chroma_quita_los_none():
    m = metadata().a_chroma()
    assert m["seccion"] == "4.5" and m["pagina_inicio"] == 4
    assert "atc" not in m  # era None: Chroma no acepta None
    assert all(isinstance(v, (str, int, float, bool)) for v in m.values())


def test_documento_subido_sin_datos_de_ficha():
    m = metadata(tipo_documento="documento", nregistro=None, seccion=None, titulo_seccion=None)
    assert m.a_chroma()["tipo_documento"] == "documento"


def test_validaciones_basicas():
    with pytest.raises(ValidationError):
        metadata(pagina_inicio=0)
    with pytest.raises(ValidationError):
        metadata(tipo_documento="prospecto")
    with pytest.raises(ValidationError):
        Chunk(texto="", metadata=metadata())
    with pytest.raises(ValidationError):
        QueryRequest(pregunta="?")


def test_respuesta_sin_contexto():
    r = QueryResponse(respuesta="No consta en las fichas consultadas.", encontrado=False)
    assert r.fuentes == [] and r.aviso_pii is False


def test_ida_y_vuelta_json():
    c = Chunk(texto="[Lopresor · 4.5] texto", metadata=metadata())
    assert Chunk.model_validate_json(c.model_dump_json()) == c
