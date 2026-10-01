"""Tests for the embedding model factory.

Responsible: P2 · Embeddings, vector database and retrieval.
"""

from unittest.mock import patch

from src.common.config import settings
from src.indexing.embeddings import DEFAULT_EMBEDDING_MODEL, get_embeddings


def test_default_embedding_model_matches_settings():
    """The P2 default model should come from the central application settings."""
    assert DEFAULT_EMBEDDING_MODEL == settings.EMBEDDING_MODEL


def test_get_embeddings_uses_expected_configuration():
    """The factory should configure local normalized embeddings."""
    get_embeddings.cache_clear()

    with patch("src.indexing.embeddings.HuggingFaceEmbeddings") as mock_embeddings:
        get_embeddings()

        mock_embeddings.assert_called_once_with(
            model_name=DEFAULT_EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    get_embeddings.cache_clear()


def test_get_embeddings_accepts_custom_model():
    """A different embedding model can be injected without changing the module."""
    get_embeddings.cache_clear()

    with patch("src.indexing.embeddings.HuggingFaceEmbeddings") as mock_embeddings:
        get_embeddings("intfloat/multilingual-e5-base")

        mock_embeddings.assert_called_once_with(
            model_name="intfloat/multilingual-e5-base",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    get_embeddings.cache_clear()
