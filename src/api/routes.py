# src/api/routes.py
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from src.common.schemas import (
    DocumentoIndexado,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from src.generation.rag_chain import RAGChain
from src.indexing.vector_store import add_chunks, delete_document, list_documents
from src.ingestion.catalogo import leer_catalogo
from src.ingestion.loaders import DocumentoIlegibleError, FormatoNoSoportadoError
from src.ingestion.pipeline import CATALOGO, ingest_file

router = APIRouter()

MAX_BYTES_SUBIDA = 25 * 1024 * 1024  # 25 MB: una ficha técnica ocupa menos de 2 MB


def get_rag_chain() -> RAGChain:
    return RAGChain()


def _info_catalogo(nombre_archivo: str) -> dict | None:
    """Fila del catálogo si el archivo es una ficha técnica (FT_<nregistro>.pdf), como en el pipeline de P1."""
    m = re.fullmatch(r"FT_(\d+)", Path(nombre_archivo).stem)
    if not m or not CATALOGO.exists():
        return None
    return next((f for f in leer_catalogo(CATALOGO) if f["nregistro"] == m.group(1)), None)


@router.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
def health():
    return {"status": "healthy"}


@router.post("/query", response_model=QueryResponse, tags=["RAG"])
def query(
    request: QueryRequest,
    rag_chain: RAGChain = Depends(get_rag_chain), # noqa: B008
):
    return rag_chain.answer(request)


@router.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
def ingest(file: UploadFile = File(...)):  # noqa: B008
    """Sube un PDF, TXT o MD: lo procesa con la ingesta de P1 y lo indexa con el vector store de P2.

    Si el documento ya estaba indexado (mismo doc_id) se reemplaza: `ya_existia = true`.
    """
    # El navegador puede mandar la ruta completa (C:\...\ficha.pdf): nos quedamos con el nombre.
    nombre_archivo = re.split(r"[\\/]", file.filename or "")[-1].strip()
    if not nombre_archivo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo no tiene nombre")

    contenido = file.file.read(MAX_BYTES_SUBIDA + 1)
    if len(contenido) > MAX_BYTES_SUBIDA:
        raise HTTPException(
            413,
            f"El archivo supera el máximo de {MAX_BYTES_SUBIDA // (1024 * 1024)} MB",
        )

    # P1 trabaja con rutas y deduce el nombre y el doc_id del nombre de archivo: se conserva el original.
    # En Windows, PyMuPDF deja bloqueado un PDF que no ha podido abrir mientras la excepción siga viva,
    # y borrar la carpeta temporal fallaría (WinError 32) tapando el error real con un 500. Por eso:
    # el error se guarda y se lanza DESPUÉS de salir del `with`, y la limpieza tolera fallos.
    error: tuple[int, str] | None = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as carpeta:
        ruta = Path(carpeta) / nombre_archivo
        ruta.write_bytes(contenido)
        try:
            doc, chunks = ingest_file(ruta, _info_catalogo(nombre_archivo))
        except FormatoNoSoportadoError as e:
            error = (status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(e))
        except DocumentoIlegibleError as e:
            error = (422, str(e))
    if error:
        raise HTTPException(*error)

    if not chunks:
        raise HTTPException(
            422,
            f"No se ha podido extraer texto de {nombre_archivo}",
        )

    # Reindexar = borrar lo anterior y añadir lo nuevo (así no quedan fragmentos huérfanos
    # si la nueva versión del documento tiene menos). El borrado dice si ya existía.
    ya_existia = delete_document(doc.doc_id) > 0
    add_chunks(chunks)

    return IngestResponse(
        doc_id=doc.doc_id,
        nombre=chunks[0].metadata.nombre,
        tipo_documento=chunks[0].metadata.tipo_documento,
        paginas=len(doc.paginas),
        chunks=len(chunks),
        ya_existia=ya_existia,
    )


@router.get("/documents", response_model=list[DocumentoIndexado], tags=["Documents"])
def get_documents():
    return list_documents()


@router.delete("/documents/{document_id}", tags=["Documents"])
def eliminar_documento(document_id: str):
    eliminados = delete_document(document_id)
    if not eliminados:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No hay ningún documento indexado con id {document_id}",
        )
    return {"status": "deleted", "document_id": document_id, "chunks_eliminados": eliminados}
