"""Tests for the persistent ChromaDB vector store.

Responsible: P2 · Embeddings, vector database and retrieval.
"""

from unittest.mock import MagicMock, patch

from src.common.schemas import Chunk, ChunkMetadata
from src.indexing.vector_store import (
    add_chunks,
    delete_document,
    get_vector_store,
    list_documents,
)


def make_chunk(
    chunk_id: str = "FT_00160065::2::1",
    doc_id: str = "FT_00160065",
) -> Chunk:
    """Create a representative chunk for vector store tests."""
    return Chunk(
        texto="[Aerius · 2 Composición] Cada comprimido contiene 5 mg de desloratadina.",
        metadata=ChunkMetadata(
            chunk_id=chunk_id,
            doc_id=doc_id,
            tipo_documento="ficha_tecnica",
            nombre="Aerius 5 mg",
            nregistro="00160065",
            principios_activos="DESLORATADINA",
            origen="ema",
            seccion="2",
            titulo_seccion="Composición cualitativa y cuantitativa",
            pagina_inicio=2,
            pagina_fin=2,
            orden=1,
            parte=1,
            total_partes=1,
            url_fuente="https://cima.aemps.es/example",
        ),
    )


def test_get_vector_store_uses_persistent_cosine_collection(tmp_path):
    """The store should use the requested persistent directory and cosine space."""
    fake_embeddings = MagicMock()

    with patch("src.indexing.vector_store.Chroma") as mock_chroma:
        get_vector_store(
            embedding_function=fake_embeddings,
            persist_directory=tmp_path / "chroma",
            collection_name="test_collection",
        )

        mock_chroma.assert_called_once_with(
            collection_name="test_collection",
            embedding_function=fake_embeddings,
            persist_directory=str(tmp_path / "chroma"),
            collection_metadata={"hnsw:space": "cosine"},
        )

    assert (tmp_path / "chroma").is_dir()


def test_add_chunks_uses_stable_chunk_ids_and_metadata():
    """Chunks should be upserted using their stable chunk IDs."""
    store = MagicMock()
    store.add_texts.return_value = ["FT_00160065::2::1"]
    chunk = make_chunk()

    result = add_chunks([chunk], vector_store=store)

    store.add_texts.assert_called_once_with(
        texts=[chunk.texto],
        metadatas=[chunk.metadata.a_chroma()],
        ids=[chunk.metadata.chunk_id],
    )
    assert result == ["FT_00160065::2::1"]


def test_add_chunks_returns_empty_list_for_empty_input():
    """Empty input should not access Chroma."""
    store = MagicMock()

    result = add_chunks([], vector_store=store)

    assert result == []
    store.add_texts.assert_not_called()


def test_delete_document_removes_all_matching_chunk_ids():
    """Deleting a document should delete all chunks belonging to it."""
    store = MagicMock()
    store.get.return_value = {
        "ids": [
            "FT_00160065::1::1",
            "FT_00160065::2::1",
        ]
    }

    deleted = delete_document("FT_00160065", vector_store=store)

    store.get.assert_called_once_with(where={"doc_id": "FT_00160065"})
    store.delete.assert_called_once_with(
        ids=[
            "FT_00160065::1::1",
            "FT_00160065::2::1",
        ]
    )
    assert deleted == 2


def test_delete_document_does_nothing_when_document_is_missing():
    """Missing documents should report zero deleted chunks."""
    store = MagicMock()
    store.get.return_value = {"ids": []}

    deleted = delete_document("FT_UNKNOWN", vector_store=store)

    store.delete.assert_not_called()
    assert deleted == 0


def test_list_documents_groups_chunks_by_document():
    """Document listing should aggregate the number of stored chunks."""
    store = MagicMock()
    store.get.return_value = {
        "metadatas": [
            {
                "doc_id": "FT_00160065",
                "nombre": "Aerius 5 mg",
                "tipo_documento": "ficha_tecnica",
            },
            {
                "doc_id": "FT_00160065",
                "nombre": "Aerius 5 mg",
                "tipo_documento": "ficha_tecnica",
            },
            {
                "doc_id": "FT_99999999",
                "nombre": "Otro medicamento",
                "tipo_documento": "ficha_tecnica",
            },
        ]
    }

    documents = list_documents(vector_store=store)

    assert documents == [
        {
            "doc_id": "FT_00160065",
            "nombre": "Aerius 5 mg",
            "tipo_documento": "ficha_tecnica",
            "chunks": 2,
        },
        {
            "doc_id": "FT_99999999",
            "nombre": "Otro medicamento",
            "tipo_documento": "ficha_tecnica",
            "chunks": 1,
        },
    ]
