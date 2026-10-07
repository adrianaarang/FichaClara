"""Pipeline de ingesta: cargar → limpiar → trocear → guardar en JSONL.

Uso (desde la raíz del repo):
    python -m src.ingestion.pipeline                     # todas las fichas de data/raw
    python -m src.ingestion.pipeline --limite 5          # prueba rápida
    python -m src.ingestion.pipeline --muestra           # genera tests/fixtures/chunks_muestra.jsonl

El resultado (data/processed/chunks.jsonl) es lo que David (P2) indexa en Chroma:
una línea por chunk, en el formato de src/common/schemas.py (Chunk).

Responsable: P1 · Ingesta y chunking
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from src.common.schemas import Chunk
from src.ingestion.catalogo import leer_catalogo
from src.ingestion.chunker import trocear_documento
from src.ingestion.cleaner import limpiar_documento
from src.ingestion.loaders import (
    EXTENSIONES_SOPORTADAS,
    DocumentoCargado,
    DocumentoIlegibleError,
    cargar_documento,
)

logger = logging.getLogger(__name__)

CATALOGO = Path("data/catalogo_medicamentos.csv")
SALIDA = Path("data/processed/chunks.jsonl")
MUESTRA = Path("tests/fixtures/chunks_muestra.jsonl")


def ingest_file(ruta: Path | str, info: dict | None = None) -> tuple[DocumentoCargado, list[Chunk]]:
    """Procesa un documento completo. Es lo que usará el endpoint /ingest de Josema (P3).

    Lanza DocumentoIlegibleError / FormatoNoSoportadoError si no se puede leer.
    """
    doc = limpiar_documento(cargar_documento(ruta))
    return doc, trocear_documento(doc, info)


def guardar_chunks(chunks: list[Chunk], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(c.model_dump_json() + "\n")


def leer_chunks(ruta: Path) -> list[Chunk]:
    """Para David y Yohana: carga el JSONL como objetos Chunk."""
    with ruta.open(encoding="utf-8") as f:
        return [Chunk.model_validate_json(linea) for linea in f if linea.strip()]


def ingest_folder(carpeta: Path, catalogo: Path = CATALOGO, limite: int | None = None) -> tuple[list[Chunk], dict]:
    """Procesa todos los documentos de una carpeta. No se para si uno falla."""
    info_por_registro = {fila["nregistro"]: fila for fila in leer_catalogo(catalogo)} if catalogo.exists() else {}
    archivos = sorted(f for f in carpeta.iterdir() if f.suffix.lower() in EXTENSIONES_SOPORTADAS)[:limite]

    todos: list[Chunk] = []
    resumen: dict = {"documentos": 0, "fallidos": [], "sin_secciones": [], "varias_presentaciones": [],
                     "chunks_por_seccion": Counter()}
    for n, ruta in enumerate(archivos, 1):
        print(f"[{n}/{len(archivos)}] {ruta.name}          ", end="\r", flush=True)
        nregistro = ruta.stem.removeprefix("FT_")
        try:
            doc, chunks = ingest_file(ruta, info_por_registro.get(nregistro))
        except DocumentoIlegibleError as e:
            resumen["fallidos"].append(f"{ruta.name}: {e}")
            continue
        if doc.es_ficha_tecnica and chunks and chunks[0].metadata.tipo_documento != "ficha_tecnica":
            resumen["sin_secciones"].append(ruta.name)
        if any("::p2::" in c.metadata.chunk_id for c in chunks):
            resumen["varias_presentaciones"].append(ruta.name)
        resumen["documentos"] += 1
        resumen["chunks_por_seccion"].update(c.metadata.seccion or "sin sección" for c in chunks)
        todos.extend(chunks)
    return todos, resumen


def _imprimir_resumen(chunks: list[Chunk], resumen: dict, salida: Path) -> None:
    tamanos = sorted(len(c.texto) for c in chunks) or [0]
    print("\n\n===== RESUMEN =====")
    print(f"Documentos procesados: {resumen['documentos']}")
    print(f"Chunks generados:      {len(chunks)}")
    print(f"Tamaño (caracteres):   medio {sum(tamanos) // len(tamanos)} · mediana {tamanos[len(tamanos) // 2]}"
          f" · mín {tamanos[0]} · máx {tamanos[-1]}")
    print(f"Fallidos:              {len(resumen['fallidos'])}")
    for f in resumen["fallidos"]:
        print("   ", f)
    print(f"Fichas sin secciones reconocidas (troceo genérico): {len(resumen['sin_secciones'])}")
    for f in resumen["sin_secciones"]:
        print("   ", f)
    print(f"Fichas EMA con varias presentaciones en el mismo PDF: {len(resumen['varias_presentaciones'])}")
    principales = ["4.1", "4.2", "4.3", "4.4", "4.5", "4.8"]
    print("Chunks en las secciones clave:", {s: resumen["chunks_por_seccion"][s] for s in principales})
    print(f"Guardado en: {salida}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--carpeta", type=Path, default=Path("data/raw"))
    parser.add_argument("--salida", type=Path, default=SALIDA)
    parser.add_argument("--catalogo", type=Path, default=CATALOGO)
    parser.add_argument("--limite", type=int, default=None)
    parser.add_argument("--muestra", action="store_true",
                        help=f"genera {MUESTRA} con las 5 primeras fichas (para tests de David y Yohana)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    if args.muestra:
        args.limite, args.salida = 5, MUESTRA
    chunks, resumen = ingest_folder(args.carpeta, args.catalogo, args.limite)
    guardar_chunks(chunks, args.salida)
    _imprimir_resumen(chunks, resumen, args.salida)
    if args.muestra:
        print(json.dumps({"ejemplo": chunks[0].model_dump()}, ensure_ascii=False, indent=2)[:1200])


if __name__ == "__main__":
    main()
