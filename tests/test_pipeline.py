"""Tests del pipeline de ingesta.

Responsable: Adriana (P1)
"""
import shutil
from pathlib import Path

from src.ingestion.pipeline import (
    guardar_chunks,
    ingest_file,
    ingest_folder,
    leer_chunks,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_file_y_jsonl_ida_y_vuelta(tmp_path: Path):
    doc, chunks = ingest_file(FIXTURES / "FT_11265.pdf", {"nombre": "Acfol 5 mg comprimidos"})
    assert doc.doc_id == "FT_11265" and len(chunks) > 20
    salida = tmp_path / "chunks.jsonl"
    guardar_chunks(chunks, salida)
    assert leer_chunks(salida) == chunks


def test_ingest_folder_no_se_para_si_un_archivo_falla(tmp_path: Path):
    shutil.copy(FIXTURES / "FT_11265.pdf", tmp_path)
    (tmp_path / "roto.pdf").write_bytes(b"no es un pdf")
    chunks, resumen = ingest_folder(tmp_path, catalogo=tmp_path / "no_existe.csv")
    assert resumen["documentos"] == 1 and len(resumen["fallidos"]) == 1
    assert chunks and all(c.metadata.doc_id == "FT_11265" for c in chunks)
