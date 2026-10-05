"""Vincula cada pregunta del golden set con los chunk_id relevantes y detecta huecos.

Responsable: P5 · Calidad, evaluación, DevOps y documentación

Para cada pregunta con respuesta busca en data/processed/chunks.jsonl todos los
fragmentos de la ficha (nregistro) y la sección esperadas, y los guarda en el campo
``expected_chunk_ids``. Así quien calcule hit rate o MRR por chunk (P2) tiene la
lista de fragmentos relevantes, y quien mantiene el golden set (P5) detecta al
momento una pregunta cuya ficha o sección no existe en el índice.

Uso (desde la raíz del repo):
    python -m evaluation.vincular_chunks              # solo informa
    python -m evaluation.vincular_chunks --escribir   # añade expected_chunk_ids

Código de salida 1 si alguna pregunta con respuesta no tiene ningún chunk.
Esto comprueba que la sección EXISTE, no que su texto responda a la pregunta: eso
sigue requiriendo la revisión manual (campo ``verificado``).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from evaluation.eval_retrieval import (
    CHUNKS_POR_DEFECTO,
    GOLDEN_POR_DEFECTO,
    cargar_golden,
)


def indexar_chunks(ruta: Path) -> dict[tuple[str, str], list[str]]:
    """(nregistro, seccion) -> chunk_id de todos los fragmentos, en orden."""
    if not ruta.is_file():
        raise FileNotFoundError(
            f"No existe {ruta}. Genera los chunks con: python -m src.ingestion.pipeline"
        )
    indice: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            meta = json.loads(linea)["metadata"]
            clave = (str(meta.get("nregistro")), str(meta.get("seccion")))
            indice[clave].append((meta.get("orden", 0), meta["chunk_id"]))
    return {k: [cid for _, cid in sorted(v)] for k, v in indice.items()}


def vincular(
    golden: list[dict], indice: dict[tuple[str, str], list[str]]
) -> tuple[list[dict], list[dict]]:
    """Devuelve (golden con expected_chunk_ids, preguntas sin chunks)."""
    huecos = []
    resultado = []
    for g in golden:
        g = dict(g)
        if g.get("answerable"):
            ids = indice.get((g["expected_nregistro"], g["expected_seccion"]), [])
            g["expected_chunk_ids"] = ids
            if not ids:
                huecos.append(g)
        resultado.append(g)
    return resultado, huecos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--golden", type=Path, default=GOLDEN_POR_DEFECTO)
    p.add_argument("--chunks", type=Path, default=CHUNKS_POR_DEFECTO)
    p.add_argument(
        "--escribir",
        action="store_true",
        help="reescribe el golden set con expected_chunk_ids",
    )
    args = p.parse_args(argv)

    golden = cargar_golden(args.golden)
    vinculado, huecos = vincular(golden, indexar_chunks(args.chunks))

    con_respuesta = [g for g in vinculado if g.get("answerable")]
    print(f"Preguntas con respuesta: {len(con_respuesta)}")
    print(f"  con chunks en el índice: {len(con_respuesta) - len(huecos)}")
    for g in vinculado:
        if g.get("answerable"):
            n = len(g["expected_chunk_ids"])
            print(
                f"  {g['id']}  {g['expected_nregistro']:<10} {g['expected_seccion']:<4} "
                f"-> {n} chunk(s)" + ("   <-- SIN CHUNKS" if n == 0 else "")
            )
    if huecos:
        print(
            "\nRevisa estas preguntas: la ficha o la sección no está en los chunks "
            "(ficha no descargada, sección no detectada o sección mal puesta en el "
            "golden set):",
            ", ".join(g["id"] for g in huecos),
        )

    if args.escribir:
        with args.golden.open("w", encoding="utf-8") as f:
            for g in vinculado:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")
        print(f"\nActualizado: {args.golden}")
    return 1 if huecos else 0


if __name__ == "__main__":
    sys.exit(main())
