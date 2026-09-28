"""Experimento: troceo fijo (500 / 1.000 caracteres) frente a troceo por sección.

Compara nuestra estrategia de chunking (una sección de la ficha = un chunk, ver
chunker.py) con un troceo "ingenuo" por tamaño fijo, sobre el mismo texto ya limpio.
El objetivo es dar una tabla de resultados que justifique por qué trocear por
sección es mejor para este caso de uso (ver docs/chunking.md).

Métrica clave: cuántos chunks mezclan contenido de más de una sección numerada
(p. ej. "4.5 Interacciones" y "4.6 Embarazo" en el mismo fragmento). Es justo lo
que el troceo por sección evita por construcción, y el motivo por el que un
fragmento de 4.8 "no dice de qué fármaco habla" si se trocea por tamaño fijo.

Nota: la comparación "de verdad" (hit rate@k con el golden set de P5, ver plan del
proyecto) necesita el retriever de P2 y todavía no está disponible
(evaluation/golden_set.jsonl está vacío). Este experimento mide un proxy que no
depende de nadie más: la pureza de sección de cada chunk y si las secciones clave
quedan enteras en un único fragmento, que es la propiedad que motiva la decisión
de diseño. Cuando el golden set y el retriever existan, este script se puede
ampliar con hit rate@k por estrategia.

Uso:
    python -m src.ingestion.experimento_chunking                 # todas las fichas de data/raw
    python -m src.ingestion.experimento_chunking --limite 20
    python -m src.ingestion.experimento_chunking --carpeta tests/fixtures

Resultado: tabla en pantalla + docs/resultados/experimento_chunking.csv

Responsable: Adriana (P1)
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.ingestion.chunker import (
    ORDEN_PLANTILLA,
    PLANTILLA,
    RE_TITULO,
    es_titulo_de_seccion,
    trocear_documento,
)
from src.ingestion.cleaner import limpiar_documento
from src.ingestion.loaders import DocumentoCargado, DocumentoIlegibleError, cargar_documento

CLAVE = ("4.1", "4.2", "4.3", "4.4", "4.5", "4.8")
INFORME = Path("docs/resultados/experimento_chunking.csv")

# Overlap ~15 %, igual criterio que el troceo por sección (ver chunker.SOLAPE).
ESTRATEGIAS_FIJAS = {
    "fijo_500": 500,
    "fijo_1000": 1000,
}


@dataclass
class ResultadoEstrategia:
    nombre: str
    n_chunks: int
    tamano_medio: int
    pct_mezcla: float          # % de chunks que tocan >1 sección numerada distinta
    pct_clave_entera: float    # % de secciones clave que caben enteras en un único chunk


# ---------------------------------------------------------------- texto global etiquetado por sección

def _spans_secciones(doc: DocumentoCargado) -> list[tuple[int, int, str | None]]:
    """(inicio, fin, numero_seccion) de cada tramo del texto completo del documento.

    Usa la misma regla de aceptación de títulos que detectar_secciones() (chunker.py),
    pero sobre el texto global (doc.texto_completo) en vez de por sección, para poder
    comparar con los chunks de tamaño fijo, que no respetan esos límites.
    """
    spans: list[tuple[int, int, str | None]] = []
    offset = 0
    inicio_tramo = 0
    numero_actual: str | None = None
    ultimo = -1  # posición en ORDEN_PLANTILLA del último título aceptado

    for pagina in doc.paginas:
        for linea in pagina.texto.split("\n"):
            m = RE_TITULO.match(linea.strip())
            if m:
                numero, titulo = m.group(1), m.group(2).strip()
                pos = ORDEN_PLANTILLA.index(numero) if numero in PLANTILLA else -1
                if pos > ultimo and es_titulo_de_seccion(numero, titulo):
                    spans.append((inicio_tramo, offset, numero_actual))
                    inicio_tramo = offset
                    numero_actual = numero
                    ultimo = pos
            offset += len(linea) + 1  # +1 por el "\n" que vuelve a poner texto_completo
    spans.append((inicio_tramo, offset, numero_actual))
    return spans


def _secciones_en(spans: list[tuple[int, int, str | None]], inicio: int, fin: int) -> set[str]:
    """Números de sección (de la plantilla) que se solapan con [inicio, fin)."""
    return {n for ini, f, n in spans if n and ini < fin and f > inicio}


# ---------------------------------------------------------------- una estrategia sobre un documento

def _evaluar_fijo(doc: DocumentoCargado, spans: list[tuple[int, int, str | None]],
                   tam_chunk: int, solape: int) -> tuple[list[int], int, dict[str, int]]:
    """Trocea el texto completo por tamaño fijo. Devuelve tamaños, nº de chunks con mezcla
    de secciones, y para cada sección clave cuántos chunks distintos la tocan (>1 = partida)."""
    divisor = RecursiveCharacterTextSplitter(chunk_size=tam_chunk, chunk_overlap=solape,
                                             add_start_index=True,
                                             separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""])
    trozos = divisor.create_documents([doc.texto_completo])
    tamanos = [len(t.page_content) for t in trozos]
    mezclas = 0
    chunks_por_seccion: dict[str, set[int]] = {c: set() for c in CLAVE}
    for i, t in enumerate(trozos):
        inicio = t.metadata["start_index"]
        fin = inicio + len(t.page_content)
        secciones = _secciones_en(spans, inicio, fin)
        if len(secciones) > 1:
            mezclas += 1
        for numero in secciones & set(CLAVE):
            chunks_por_seccion[numero].add(i)
    return tamanos, mezclas, {n: len(ids) for n, ids in chunks_por_seccion.items()}


def evaluar_documento(doc: DocumentoCargado) -> dict[str, tuple[list[int], int, dict[str, int]]]:
    """Las tres estrategias sobre el mismo documento. Clave: nombre de la estrategia."""
    spans = _spans_secciones(doc)
    resultado = {}
    for nombre, tam in ESTRATEGIAS_FIJAS.items():
        resultado[nombre] = _evaluar_fijo(doc, spans, tam, solape=round(tam * 0.15))

    # Nuestra estrategia: por construcción no mezcla nunca, y una sección clave solo queda
    # partida si supera MAX_SECCION (se refleja en si el chunk tiene más de 1 "parte").
    chunks = trocear_documento(doc)
    tamanos = [len(c.texto) for c in chunks]
    partidas = {c.metadata.seccion: c.metadata.total_partes for c in chunks
                if c.metadata.seccion in CLAVE}
    chunks_por_seccion = {n: (1 if partidas.get(n, 1) == 1 else 2) for n in CLAVE if n in partidas}
    # (partidas.get==1 → 1 sola parte, cabe en un chunk; >1 → como mínimo 2, se cuenta como "partida")
    resultado["por_seccion"] = (tamanos, 0, chunks_por_seccion)
    return resultado


# ---------------------------------------------------------------- agregación

def resumir(nombre: str, acumulado: list[tuple[list[int], int, dict[str, int]]]) -> ResultadoEstrategia:
    tamanos = [t for tams, _, _ in acumulado for t in tams]
    n_chunks = len(tamanos)
    mezclas = sum(m for _, m, _ in acumulado)
    claves_totales, claves_enteras = 0, 0
    for _, _, por_seccion in acumulado:
        for n, n_chunks_seccion in por_seccion.items():
            claves_totales += 1
            if n_chunks_seccion <= 1:
                claves_enteras += 1
    return ResultadoEstrategia(
        nombre=nombre,
        n_chunks=n_chunks,
        tamano_medio=sum(tamanos) // n_chunks if n_chunks else 0,
        pct_mezcla=mezclas / n_chunks * 100 if n_chunks else 0.0,
        pct_clave_entera=claves_enteras / claves_totales * 100 if claves_totales else 0.0,
    )


def ejecutar(carpeta: Path, limite: int | None = None) -> list[ResultadoEstrategia]:
    archivos = sorted(carpeta.glob("FT_*.pdf"))[:limite]
    por_estrategia: dict[str, list] = {"fijo_500": [], "fijo_1000": [], "por_seccion": []}
    for n, ruta in enumerate(archivos, 1):
        print(f"[{n}/{len(archivos)}] {ruta.name}          ", end="\r", flush=True)
        try:
            doc = limpiar_documento(cargar_documento(ruta))
        except DocumentoIlegibleError as e:
            print(f"\n  {ruta.name}: {e}")
            continue
        if not doc.es_ficha_tecnica:
            continue
        for nombre, res in evaluar_documento(doc).items():
            por_estrategia[nombre].append(res)
    return [resumir(nombre, acumulado) for nombre, acumulado in por_estrategia.items()]


def guardar_informe(resultados: list[ResultadoEstrategia], ruta: Path = INFORME) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["estrategia", "n_chunks", "tamano_medio", "pct_chunks_con_mezcla_secciones",
                    "pct_secciones_clave_enteras"])
        for r in resultados:
            w.writerow([r.nombre, r.n_chunks, r.tamano_medio, f"{r.pct_mezcla:.1f}", f"{r.pct_clave_entera:.1f}"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--carpeta", type=Path, default=Path("data/raw"))
    parser.add_argument("--limite", type=int, default=None)
    args = parser.parse_args()

    resultados = ejecutar(args.carpeta, args.limite)
    guardar_informe(resultados)

    print("\n\n===== EXPERIMENTO DE CHUNKING: fijo 500 / fijo 1.000 / por sección =====")
    print(f"{'estrategia':<12} {'nº chunks':>10} {'tamaño medio':>13} {'% con mezcla de secciones':>27} "
          f"{'% clave entera en 1 chunk':>27}")
    for r in resultados:
        print(f"{r.nombre:<12} {r.n_chunks:>10} {r.tamano_medio:>13} {r.pct_mezcla:>26.1f}% "
              f"{r.pct_clave_entera:>26.1f}%")
    print(f"\nInforme completo: {INFORME}")


if __name__ == "__main__":
    main()
