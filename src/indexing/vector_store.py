"""Persistent ChromaDB vector store for FichaClara.

Responsible: P2 · Embeddings, vector database and retrieval.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from src.common.schemas import Chunk
from src.indexing.embeddings import get_embeddings

DEFAULT_CHROMA_DIR = "data/chroma"
DEFAULT_CHROMA_COLLECTION = "fichas_tecnicas"


def get_vector_store(
    embedding_function: Embeddings | None = None,
    persist_directory: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_CHROMA_COLLECTION,
) -> Chroma:
    """Create or open the persistent Chroma collection.

    Args:
        embedding_function: Embedding implementation used by Chroma.
        persist_directory: Directory where Chroma stores its persistent data.
        collection_name: Name of the Chroma collection.

    Returns:
        A persistent Chroma vector store configured for cosine distance.
    """
    path = Path(persist_directory)
    path.mkdir(parents=True, exist_ok=True)

    if embedding_function is None:
        embedding_function = get_embeddings()

    return Chroma(
        collection_name=collection_name,
        embedding_function=embedding_function,
        persist_directory=str(path),
        collection_metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    chunks: Iterable[Chunk],
    *,
    vector_store: Chroma | None = None,
    embedding_function: Embeddings | None = None,
    persist_directory: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_CHROMA_COLLECTION,
) -> list[str]:
    """Add or update chunks using their stable chunk IDs.

    Chroma's ``add_texts`` uses upsert internally. Therefore, indexing the same
    ``chunk_id`` again updates the existing entry instead of creating a
    duplicate.
    """
    chunk_list = list(chunks)
    if not chunk_list:
        return []

    store = vector_store or get_vector_store(
        embedding_function=embedding_function,
        persist_directory=persist_directory,
        collection_name=collection_name,
    )

    return store.add_texts(
        texts=[chunk.texto for chunk in chunk_list],
        metadatas=[chunk.metadata.a_chroma() for chunk in chunk_list],
        ids=[chunk.metadata.chunk_id for chunk in chunk_list],
    )


def delete_document(
    doc_id: str,
    *,
    vector_store: Chroma | None = None,
    embedding_function: Embeddings | None = None,
    persist_directory: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_CHROMA_COLLECTION,
) -> int:
    """Delete every indexed chunk belonging to one document.

    Returns:
        Number of chunks deleted.
    """
    store = vector_store or get_vector_store(
        embedding_function=embedding_function,
        persist_directory=persist_directory,
        collection_name=collection_name,
    )

    result = store.get(where={"doc_id": doc_id})
    ids = result.get("ids") or []

    if ids:
        store.delete(ids=ids)

    return len(ids)


def list_documents(
    *,
    vector_store: Chroma | None = None,
    embedding_function: Embeddings | None = None,
    persist_directory: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_CHROMA_COLLECTION,
) -> list[dict[str, Any]]:
    """List indexed documents and the number of chunks stored for each one."""
    store = vector_store or get_vector_store(
        embedding_function=embedding_function,
        persist_directory=persist_directory,
        collection_name=collection_name,
    )

    result = store.get(include=["metadatas"])
    documents: dict[str, dict[str, Any]] = {}

    for metadata in result.get("metadatas") or []:
        if not metadata:
            continue

        doc_id = metadata.get("doc_id")
        if not doc_id:
            continue

        if doc_id not in documents:
            documents[doc_id] = {
                "doc_id": doc_id,
                "nombre": metadata.get("nombre", ""),
                "tipo_documento": metadata.get("tipo_documento", "documento"),
                "chunks": 0,
            }

        documents[doc_id]["chunks"] += 1

    return sorted(
        documents.values(),
        key=lambda document: str(document["nombre"]).lower(),
    )
