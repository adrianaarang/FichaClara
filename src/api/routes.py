# src/api/routes.py
from fastapi import APIRouter, Depends, status

from src.common.schemas import (
    DocumentoIndexado,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from src.generation.rag_chain import RAGChain

router = APIRouter()


def get_rag_chain() -> RAGChain:
    return RAGChain()


@router.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
def health():
    return {"status": "healthy"}


@router.post("/query", response_model=QueryResponse, tags=["RAG"])
def query(
    request: QueryRequest,
    rag_chain: RAGChain = Depends(get_rag_chain),
):
    return rag_chain.answer(request)


@router.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
def ingest():
    # TODO: Conectar extractor de P1 e indexador de P2
    return IngestResponse(
        doc_id="doc_demo",
        nombre="Documento Demo",
        tipo_documento="ficha_tecnica",
        paginas=1,
        chunks=1,
        ya_existia=False,
    )


@router.get("/documents", response_model=list[DocumentoIndexado], tags=["Documents"])
def get_documents():
    # TODO: Conectar con ChromaDB de P2
    return []


@router.delete("/documents/{document_id}", tags=["Documents"])
def delete_document(document_id: str):
    return {"status": "deleted", "document_id": document_id}