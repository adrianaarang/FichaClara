"""Embedding model factory for FichaClara.

Responsible: P2 · Embeddings, vector database and retrieval.
"""

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"


@lru_cache(maxsize=4)
def get_embeddings(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    device: str = "cpu",
) -> HuggingFaceEmbeddings:
    """Create and cache a local Hugging Face embedding model.

    Args:
        model_name: Hugging Face model identifier.
        device: Device used to run the embedding model, such as "cpu" or "cuda".

    Returns:
        A configured HuggingFaceEmbeddings instance.

    Notes:
        Configuration is passed explicitly so this module does not depend on
        the application's environment/settings implementation.

        Embeddings are normalized because retrieval will use cosine
        similarity, where higher similarity means greater relevance.
    """
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )
