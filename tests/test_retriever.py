"""Tests for vector retrieval."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from src.retrieval.retriever import retrieve

CATALOG_CONTENT = """principio_activo_buscado,nregistro,nombre,principios_activos
sitagliptina,07383014,JANUVIA 100 MG COMPRIMIDOS RECUBIERTOS CON PELICULA,SITAGLIPTINA FOSFATO MONOHIDRATO
omeprazol,64004,GASTROMEL 20 MG CAPSULAS DURAS GASTRORRESISTENTES EFG,OMEPRAZOL
"""


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    """Create a deterministic medication catalogue."""
    path = tmp_path / "catalog.csv"
    path.write_text(CATALOG_CONTENT, encoding="utf-8")
    return path


def make_document(
    *,
    chunk_id: str = "FT_07383014::4.1::1",
    nregistro: str = "07383014",
    texto: str = "Januvia está indicado para el tratamiento de la diabetes.",
) -> Document:
    """Create a LangChain document compatible with ChunkMetadata."""
    return Document(
        page_content=texto,
        metadata={
            "chunk_id": chunk_id,
            "doc_id": f"FT_{nregistro}",
            "tipo_documento": "ficha_tecnica",
            "nombre": "JANUVIA 100 MG COMPRIMIDOS RECUBIERTOS CON PELICULA",
            "nregistro": nregistro,
            "principios_activos": "SITAGLIPTINA FOSFATO MONOHIDRATO",
            "origen": "aemps",
            "seccion": "4.1",
            "titulo_seccion": "Indicaciones terapéuticas",
            "pagina_inicio": 2,
            "pagina_fin": 2,
            "orden": 1,
        },
    )


def test_retrieve_filters_by_detected_medication(catalog_path: Path) -> None:
    store = MagicMock()
    document = make_document()

    store.similarity_search_with_relevance_scores.return_value = [
        (document, 0.91),
    ]

    result = retrieve(
        "¿Para qué está indicado Januvia?",
        k=5,
        vector_store=store,
        catalog_path=catalog_path,
    )

    store.similarity_search_with_relevance_scores.assert_called_once_with(
        "¿Para qué está indicado Januvia?",
        k=5,
        filter={"nregistro": "07383014"},
    )

    assert len(result) == 1
    assert result[0].chunk.metadata.nregistro == "07383014"
    assert result[0].score == pytest.approx(0.91)


def test_retrieve_without_medication_uses_no_filter(catalog_path: Path) -> None:
    store = MagicMock()
    store.similarity_search_with_relevance_scores.return_value = []

    result = retrieve(
        "¿Qué efectos adversos graves aparecen en las fichas?",
        vector_store=store,
        catalog_path=catalog_path,
    )

    store.similarity_search_with_relevance_scores.assert_called_once_with(
        "¿Qué efectos adversos graves aparecen en las fichas?",
        k=5,
        filter=None,
    )

    assert result == []


def test_retrieve_applies_relevance_threshold(catalog_path: Path) -> None:
    store = MagicMock()

    high_score = make_document(
        chunk_id="FT_07383014::4.1::1",
        texto="Resultado relevante.",
    )
    low_score = make_document(
        chunk_id="FT_07383014::4.2::1",
        texto="Resultado poco relevante.",
    )

    store.similarity_search_with_relevance_scores.return_value = [
        (high_score, 0.82),
        (low_score, 0.39),
    ]

    result = retrieve(
        "¿Para qué está indicado Januvia?",
        relevance_threshold=0.60,
        vector_store=store,
        catalog_path=catalog_path,
    )

    assert len(result) == 1
    assert result[0].chunk.metadata.chunk_id == "FT_07383014::4.1::1"
    assert result[0].score == pytest.approx(0.82)


def test_retrieve_converts_document_to_shared_schema(
    catalog_path: Path,
) -> None:
    store = MagicMock()
    document = make_document()

    store.similarity_search_with_relevance_scores.return_value = [
        (document, 0.75),
    ]

    result = retrieve(
        "¿Para qué está indicado Januvia?",
        vector_store=store,
        catalog_path=catalog_path,
    )

    assert result[0].chunk.texto == document.page_content
    assert result[0].chunk.metadata.nombre.startswith("JANUVIA")
    assert result[0].chunk.metadata.seccion == "4.1"
    assert result[0].score == pytest.approx(0.75)


def test_retrieve_clamps_score_to_public_contract(
    catalog_path: Path,
) -> None:
    store = MagicMock()
    document = make_document()

    store.similarity_search_with_relevance_scores.return_value = [
        (document, 1.05),
    ]

    result = retrieve(
        "¿Para qué está indicado Januvia?",
        vector_store=store,
        catalog_path=catalog_path,
    )

    assert result[0].score == 1.0


def test_blank_question_returns_empty_without_search(
    catalog_path: Path,
) -> None:
    store = MagicMock()

    result = retrieve(
        "   ",
        vector_store=store,
        catalog_path=catalog_path,
    )

    assert result == []
    store.similarity_search_with_relevance_scores.assert_not_called()


@pytest.mark.parametrize("k", [0, -1])
def test_invalid_k_raises(k: int, catalog_path: Path) -> None:
    with pytest.raises(ValueError, match="k must be greater"):
        retrieve(
            "Januvia",
            k=k,
            vector_store=MagicMock(),
            catalog_path=catalog_path,
        )


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_invalid_threshold_raises(
    threshold: float,
    catalog_path: Path,
) -> None:
    with pytest.raises(ValueError, match="relevance_threshold"):
        retrieve(
            "Januvia",
            relevance_threshold=threshold,
            vector_store=MagicMock(),
            catalog_path=catalog_path,
        )
