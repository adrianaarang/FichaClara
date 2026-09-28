"""Build the persistent Chroma index from processed FichaClara chunks.

Usage from the repository root:
    python -m scripts.build_index

For development with the sample fixture:
    python -m scripts.build_index \
        --input tests/fixtures/chunks_muestra.jsonl \
        --persist-directory /tmp/fichaclara_chroma

Responsible: P2 · Embeddings, vector database and retrieval.
"""

import argparse
import logging
from pathlib import Path

from pydantic import ValidationError

from src.common.schemas import Chunk
from src.indexing.embeddings import DEFAULT_EMBEDDING_MODEL, get_embeddings
from src.indexing.vector_store import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_CHROMA_DIR,
    add_chunks,
    get_vector_store,
)

logger = logging.getLogger(__name__)

DEFAULT_INPUT = Path("data/processed/chunks.jsonl")
DEFAULT_BATCH_SIZE = 32


def load_chunks(path: Path) -> list[Chunk]:
    """Load and validate chunks from a JSONL file."""
    if not path.is_file():
        raise FileNotFoundError(f"Chunk file not found: {path}")

    chunks: list[Chunk] = []

    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                chunks.append(Chunk.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid chunk at {path}:{line_number}: {exc}"
                ) from exc

    return chunks


def build_index(
    chunks: list[Chunk],
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    device: str = "cpu",
    persist_directory: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_CHROMA_COLLECTION,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Embed and index chunks in batches.

    Returns:
        Number of indexed chunks.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    if not chunks:
        return 0

    embeddings = get_embeddings(
        model_name=model_name,
        device=device,
    )
    vector_store = get_vector_store(
        embedding_function=embeddings,
        persist_directory=persist_directory,
        collection_name=collection_name,
    )

    indexed = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        ids = add_chunks(batch, vector_store=vector_store)
        indexed += len(ids)

        logger.info(
            "Indexed %d/%d chunks",
            indexed,
            len(chunks),
        )

    return indexed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="JSONL file containing processed chunks.",
    )
    parser.add_argument(
        "--persist-directory",
        type=Path,
        default=Path(DEFAULT_CHROMA_DIR),
        help="Directory used for persistent Chroma data.",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_CHROMA_COLLECTION,
        help="Chroma collection name.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Hugging Face embedding model.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help='Embedding device, for example "cpu" or "cuda".',
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of chunks indexed per batch.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        chunks = load_chunks(args.input)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    if not chunks:
        raise SystemExit(f"No chunks found in {args.input}")

    indexed = build_index(
        chunks,
        model_name=args.model,
        device=args.device,
        persist_directory=args.persist_directory,
        collection_name=args.collection,
        batch_size=args.batch_size,
    )

    print("\n===== INDEX SUMMARY =====")
    print(f"Source: {args.input}")
    print(f"Chunks indexed: {indexed}")
    print(f"Collection: {args.collection}")
    print(f"Persistent directory: {args.persist_directory}")
    print(f"Embedding model: {args.model}")
    print(f"Device: {args.device}")


if __name__ == "__main__":
    main()
