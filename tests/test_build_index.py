"""Tests for the Chroma index build script.

Responsible: P2 · Embeddings, vector database and retrieval.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.build_index import build_index, load_chunks
from src.common.schemas import Chunk

SAMPLE_CHUNKS = Path("tests/fixtures/chunks_muestra.jsonl")


def test_load_chunks_reads_and_validates_sample_fixture():
    """The sample JSONL produced by P1 should load as validated Chunk objects."""
    chunks = load_chunks(SAMPLE_CHUNKS)

    assert chunks
    assert all(isinstance(chunk, Chunk) for chunk in chunks)
    assert chunks[0].metadata.chunk_id
    assert chunks[0].texto


def test_load_chunks_rejects_invalid_jsonl(tmp_path):
    """Invalid chunk data should identify the failing line."""
    path = tmp_path / "invalid_chunks.jsonl"
    path.write_text('{"invalid": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"invalid_chunks\.jsonl:1"):
        load_chunks(path)


def test_build_index_indexes_chunks_in_batches():
    """Chunks should be indexed in batches using one shared vector store."""
    chunks = load_chunks(SAMPLE_CHUNKS)[:5]
    fake_embeddings = MagicMock()
    fake_store = MagicMock()

    def fake_add_chunks(batch, *, vector_store):
        assert vector_store is fake_store
        return [chunk.metadata.chunk_id for chunk in batch]

    with (
        patch(
            "scripts.build_index.get_embeddings",
            return_value=fake_embeddings,
        ) as mock_get_embeddings,
        patch(
            "scripts.build_index.get_vector_store",
            return_value=fake_store,
        ) as mock_get_vector_store,
        patch(
            "scripts.build_index.add_chunks",
            side_effect=fake_add_chunks,
        ) as mock_add_chunks,
    ):
        indexed = build_index(
            chunks,
            model_name="test-model",
            device="cpu",
            persist_directory="test-chroma",
            collection_name="test-collection",
            batch_size=2,
        )

    assert indexed == 5
    assert mock_add_chunks.call_count == 3

    mock_get_embeddings.assert_called_once_with(
        model_name="test-model",
        device="cpu",
    )
    mock_get_vector_store.assert_called_once_with(
        embedding_function=fake_embeddings,
        persist_directory="test-chroma",
        collection_name="test-collection",
    )


def test_build_index_returns_zero_for_empty_input():
    """An empty chunk list should not initialize the embedding model."""
    with patch("scripts.build_index.get_embeddings") as mock_get_embeddings:
        indexed = build_index([])

    assert indexed == 0
    mock_get_embeddings.assert_not_called()


def test_build_index_rejects_invalid_batch_size():
    """Batch size must always be at least one."""
    with pytest.raises(ValueError, match="batch_size must be at least 1"):
        build_index([], batch_size=0)
