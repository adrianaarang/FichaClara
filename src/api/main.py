"""App FastAPI.

Responsable: P3 · Orquestación LLM y API
"""

# TODO:
#   - crear app, CORS, registrar rutas
# src/api/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.common.schemas import (
    DocumentoIndexado,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from src.generation.rag_chain import RAGChain

app = FastAPI(
    title="FichaClara API",
    description="API para orquestación de RAG sobre Fichas Técnicas",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_chain = RAGChain()

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    try:
        return rag_chain.answer(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/ingest", response_model=IngestResponse)
def ingest():
    # TODO: Conectar extractor de P1 e indexador de P2
    return IngestResponse(
        doc_id="doc_demo",
        nombre="Documento Demo",
        tipo_documento="ficha_tecnica",
        paginas=1,
        chunks=1,
        ya_existia=False
    )

@app.get("/documents", response_model=list[DocumentoIndexado])
def get_documents():
    # TODO: Conectar con ChromaDB de P2
    return []

@app.delete("/documents/{document_id}")
def delete_document(document_id: str):
    return {"status": "deleted", "document_id": document_id}