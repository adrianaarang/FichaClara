"""Vector retrieval for FichaClara.

Retrieves the most relevant chunks from ChromaDB, optionally restricting the
search to the medication detected in the user's question.

Responsible: P2 · Embeddings, vector database and retrieval.
"""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.common.config import settings
from src.common.schemas import Chunk, ChunkMetadata, RetrievedChunk
from src.indexing.vector_store import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_CHROMA_DIR,
    get_vector_store,
)
from src.retrieval.query_parser import DEFAULT_CATALOG_PATH, find_medications

DEFAULT_K = settings.RETRIEVER_K
DEFAULT_RELEVANCE_THRESHOLD = settings.RELEVANCE_THRESHOLD


def _normalize_relevance_score(score: float) -> float:
    """Clamp a cosine relevance score to the public 0-1 contract."""
    return max(0.0, min(1.0, float(score)))


def _to_retrieved_chunk(
    document: Document,
    score: float,
) -> RetrievedChunk:
    """Convert a LangChain document into the shared retrieval contract."""
    metadata = ChunkMetadata.model_validate(document.metadata)

    chunk = Chunk(
        texto=document.page_content,
        metadata=metadata,
    )

    return RetrievedChunk(
        chunk=chunk,
        score=_normalize_relevance_score(score),
    )


def retrieve(
    question: str,
    k: int = DEFAULT_K,
    *,
    relevance_threshold: float | None = DEFAULT_RELEVANCE_THRESHOLD,
    vector_store: Chroma | None = None,
    embedding_function: Embeddings | None = None,
    persist_directory: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_CHROMA_COLLECTION,
    catalog_path: str | Path = DEFAULT_CATALOG_PATH,
) -> list[RetrievedChunk]:
    """Retrieve the most relevant chunks for a user question.

    The query parser first tries to identify a medication. When one medication
    is identified unambiguously, retrieval is restricted to chunks whose
    ``nregistro`` matches that medication.

    Chroma is configured with cosine distance. LangChain's relevance API
    converts cosine distance to ``1 - distance``, so higher values represent
    greater relevance. The public FichaClara contract exposes scores in the
    range 0-1.

    Args:
        question: User question to retrieve context for.
        k: Maximum number of chunks to retrieve.
        relevance_threshold: Minimum relevance score accepted. ``None`` keeps
            all top-k results without applying a global score threshold.
        vector_store: Optional existing Chroma instance, useful for dependency
            injection and tests.
        embedding_function: Embedding model used when opening Chroma.
        persist_directory: Persistent Chroma directory.
        collection_name: Chroma collection name.
        catalog_path: Medication catalogue used by the query parser.

    Returns:
        Retrieved chunks ordered from most to least relevant. Returns an empty
        list when the question is blank, Chroma finds nothing, or every result
        falls below the configured relevance threshold.

    Raises:
        ValueError: If ``k`` is less than 1 or the relevance threshold is
            outside the 0-1 range.
    """
    if not question.strip():
        return []

    if k < 1:
        raise ValueError("k must be greater than or equal to 1")

    if relevance_threshold is not None and not 0.0 <= relevance_threshold <= 1.0:
        raise ValueError("relevance_threshold must be between 0 and 1")

    medications = find_medications(
        question,
        catalog_path=catalog_path,
    )

    # No known medication means there is no grounded technical sheet to search.
    if not medications:
        return []

    store = vector_store or get_vector_store(
        embedding_function=embedding_function,
        persist_directory=persist_directory,
        collection_name=collection_name,
    )

    # One medication can be safely restricted to its technical sheet.
    # Multiple medications keep the global search so interaction questions work.
    metadata_filter = (
        {"nregistro": medications[0].registration_number}
        if len(medications) == 1
        else None
    )

    results = store.similarity_search_with_relevance_scores(
        question,
        k=k,
        filter=metadata_filter,
    )

    retrieved: list[RetrievedChunk] = []

    for document, score in results:
        normalized_score = _normalize_relevance_score(score)

        if (
            relevance_threshold is not None
            and normalized_score < relevance_threshold
        ):
            continue

        retrieved.append(
            _to_retrieved_chunk(
                document,
                normalized_score,
            )
        )

    return retrieved
