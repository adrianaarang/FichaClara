"""Hit rate@k y MRR sobre el golden set (checkpoint de retrieval).

Responsable: P5 · Calidad, evaluación, DevOps y documentación

Mide si el retriever devuelve, entre sus k primeros fragmentos, uno de la ficha
(nregistro) y la sección esperadas, y si devuelve lista vacía cuando la pregunta no
tiene respuesta en las fichas.

Uso (desde la raíz del repo):
    # línea base sin embeddings: BM25 sobre chunks.jsonl (funciona desde el día 4)
    python -m evaluation.eval_retrieval --retriever bm25

    # retriever real de P2: retrieve(question, k) de src/retrieval/retriever.py
    python -m evaluation.eval_retrieval --retriever real --etiqueta bge-m3

    # barrido de umbral (ejecutar con RELEVANCE_THRESHOLD vacío o a 0 para ver
    # todas las puntuaciones) y sugerencia de umbral para P2
    python -m evaluation.eval_retrieval --retriever real --barrido-umbral

Salida: tabla en pantalla + docs/resultados/eval_retrieval_<etiqueta>.json y
docs/resultados/eval_retrieval_<etiqueta>_preguntas.csv (detalle por pregunta).

Las preguntas se pasan antes por el filtro PII (como hará la API), salvo --sin-pii.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.common.schemas import Chunk, RetrievedChunk

RAIZ = Path(__file__).resolve().parents[1]
GOLDEN_POR_DEFECTO = RAIZ / "evaluation" / "golden_set.jsonl"
CHUNKS_POR_DEFECTO = RAIZ / "data" / "processed" / "chunks.jsonl"
RESULTADOS = RAIZ / "docs" / "resultados"

KS = (1, 3, 5)
# Categorías en las que el retriever debe devolver lista vacía. Las de consejo
# clínico y prompt injection se evalúan en eval_generation (el retriever sí puede
# devolver fragmentos de un fármaco nombrado; lo que importa es qué responde el LLM).
CATEGORIAS_RECHAZO = frozenset({"medicamento_ausente", "fuera_de_alcance"})

Retriever = Callable[[str, int], list[RetrievedChunk]]


# ------------------------------------------------------------------ golden set
def cargar_golden(ruta: Path = GOLDEN_POR_DEFECTO) -> list[dict]:
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el golden set: {ruta}")
    preguntas = []
    with ruta.open(encoding="utf-8") as f:
        for n, linea in enumerate(f, start=1):
            if linea.strip():
                try:
                    preguntas.append(json.loads(linea))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{ruta}:{n}: JSON no válido ({exc})") from exc
    return preguntas


# ------------------------------------------------------------------ resultados
@dataclass
class ResultadoPregunta:
    id: str
    pregunta: str
    categoria: str
    answerable: bool
    expected_nregistro: str | None
    expected_seccion: str | None
    # (nregistro, seccion, score) de cada fragmento devuelto, en orden
    recuperados: list[tuple[str | None, str | None, float]] = field(
        default_factory=list
    )
    enmascarada: bool = False

    def _filtrados(self, umbral: float | None, k: int):
        lista = self.recuperados
        if umbral is not None:
            lista = [r for r in lista if r[2] >= umbral]
        return lista[:k]

    def rango_acierto(self, k: int, umbral: float | None = None) -> int | None:
        """Posición (1-based) del primer fragmento de la ficha y sección esperadas."""
        for pos, (nreg, sec, _) in enumerate(self._filtrados(umbral, k), start=1):
            if nreg == self.expected_nregistro and sec == self.expected_seccion:
                return pos
        return None

    def hay_medicamento(self, k: int, umbral: float | None = None) -> bool:
        return any(
            nreg == self.expected_nregistro for nreg, _, _ in self._filtrados(umbral, k)
        )

    def seccion_top1(self, umbral: float | None = None) -> str | None:
        top = self._filtrados(umbral, 1)
        return top[0][1] if top else None

    def vacio(self, umbral: float | None = None) -> bool:
        return not self._filtrados(umbral, 10**6)


def evaluar(
    golden: list[dict],
    retriever: Retriever,
    k_max: int = 5,
    enmascarar_pii: bool = True,
) -> list[ResultadoPregunta]:
    """Ejecuta el retriever sobre todas las preguntas y guarda lo recuperado."""
    if enmascarar_pii:
        from src.guardrails.pii_filter import check_pii

    resultados = []
    for g in golden:
        pregunta = g["question"]
        enmascarada = False
        if enmascarar_pii:
            pii = check_pii(pregunta)
            if pii.contiene_pii:
                pregunta, enmascarada = pii.texto_enmascarado, True
        devueltos = retriever(pregunta, k_max)
        resultados.append(
            ResultadoPregunta(
                id=g["id"],
                pregunta=g["question"],
                categoria=g.get("categoria", ""),
                answerable=bool(g["answerable"]),
                expected_nregistro=g.get("expected_nregistro"),
                expected_seccion=g.get("expected_seccion"),
                recuperados=[
                    (
                        rc.chunk.metadata.nregistro,
                        rc.chunk.metadata.seccion,
                        float(rc.score),
                    )
                    for rc in devueltos
                ],
                enmascarada=enmascarada,
            )
        )
    return resultados


# --------------------------------------------------------------------- métricas
def _tasa(aciertos: int, total: int) -> float | None:
    return round(aciertos / total, 4) if total else None


def calcular_metricas(
    resultados: list[ResultadoPregunta],
    k_max: int = 5,
    umbral: float | None = None,
) -> dict:
    respondibles = [r for r in resultados if r.answerable]
    de_rechazo = [r for r in resultados if r.categoria in CATEGORIAS_RECHAZO]

    metricas: dict = {
        "n_preguntas": len(resultados),
        "n_respondibles": len(respondibles),
        "n_rechazo": len(de_rechazo),
        "k_max": k_max,
        "umbral": umbral,
    }
    for k in KS:
        if k > k_max:
            continue
        metricas[f"hit_rate@{k}"] = _tasa(
            sum(r.rango_acierto(k, umbral) is not None for r in respondibles),
            len(respondibles),
        )
        metricas[f"acierto_medicamento@{k}"] = _tasa(
            sum(r.hay_medicamento(k, umbral) for r in respondibles), len(respondibles)
        )

    rr = [
        1 / rango if (rango := r.rango_acierto(k_max, umbral)) else 0.0
        for r in respondibles
    ]
    metricas["mrr"] = round(sum(rr) / len(rr), 4) if rr else None
    metricas["acierto_seccion@1"] = _tasa(
        sum(r.seccion_top1(umbral) == r.expected_seccion for r in respondibles),
        len(respondibles),
    )
    metricas["rechazo_correcto"] = _tasa(
        sum(r.vacio(umbral) for r in de_rechazo), len(de_rechazo)
    )
    metricas["falsos_rechazos"] = _tasa(
        sum(r.vacio(umbral) for r in respondibles), len(respondibles)
    )

    por_seccion: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in respondibles:
        por_seccion[r.expected_seccion or "?"][0] += 1
        por_seccion[r.expected_seccion or "?"][1] += (
            r.rango_acierto(k_max, umbral) is not None
        )
    metricas["por_seccion"] = {
        sec: {"n": n, f"hit@{k_max}": _tasa(h, n)}
        for sec, (n, h) in sorted(por_seccion.items())
    }
    metricas["fallos"] = [
        r.id for r in respondibles if r.rango_acierto(k_max, umbral) is None
    ]
    return metricas


def barrido_umbral(
    resultados: list[ResultadoPregunta],
    k_max: int = 5,
    umbrales: list[float] | None = None,
) -> list[dict]:
    """Métricas para cada umbral. Sirve a P2 para calibrar RELEVANCE_THRESHOLD."""
    umbrales = umbrales or [round(i * 0.05, 2) for i in range(19)]
    filas = []
    for t in umbrales:
        m = calcular_metricas(resultados, k_max, t)
        hit = m.get(f"hit_rate@{k_max}") or 0.0
        rechazo = m["rechazo_correcto"] if m["rechazo_correcto"] is not None else 0.0
        filas.append(
            {
                "umbral": t,
                f"hit_rate@{k_max}": hit,
                "rechazo_correcto": rechazo,
                "falsos_rechazos": m["falsos_rechazos"],
                "puntuacion": round((hit + rechazo) / 2, 4),
            }
        )
    return filas


def mejor_umbral(filas: list[dict]) -> dict:
    """El umbral con mayor media de hit rate y rechazo correcto (el más bajo si empatan)."""
    return max(filas, key=lambda f: (f["puntuacion"], -f["umbral"]))


# ------------------------------------------------------------------ retrievers
def _normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c
        for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    return sin_tildes


_PARADAS = frozenset(
    {
        "de",
        "la",
        "el",
        "en",
        "y",
        "a",
        "los",
        "las",
        "un",
        "una",
        "por",
        "con",
        "para",
        "se",
        "que",
        "es",
        "del",
        "al",
        "lo",
        "su",
        "o",
        "como",
    }
)


def tokenizar(texto: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9]+", _normalizar(texto)) if t not in _PARADAS
    ]


def cargar_chunks(ruta: Path) -> list[Chunk]:
    if not ruta.is_file():
        raise FileNotFoundError(
            f"No existe {ruta}. Genera los chunks con: python -m src.ingestion.pipeline"
        )
    chunks = []
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                chunks.append(Chunk.model_validate_json(linea))
    return chunks


def crear_retriever_bm25(chunks: list[Chunk]) -> Retriever:
    """Línea base léxica (sin embeddings). Devuelve siempre k fragmentos: no rechaza.

    Su puntuación es BM25 bruto, no comparable con el coseno de P2: úsalo solo
    para comparar hit rate y MRR, no para calibrar umbrales.
    """
    from rank_bm25 import BM25Okapi

    bm25 = BM25Okapi([tokenizar(c.texto) for c in chunks])

    def retrieve(pregunta: str, k: int) -> list[RetrievedChunk]:
        puntuaciones = bm25.get_scores(tokenizar(pregunta))
        orden = sorted(range(len(chunks)), key=lambda i: puntuaciones[i], reverse=True)
        return [
            RetrievedChunk(chunk=chunks[i], score=float(puntuaciones[i]))
            for i in orden[:k]
            if puntuaciones[i] > 0
        ]

    return retrieve


def cargar_retriever_real(ruta: str = "src.retrieval.retriever:retrieve") -> Retriever:
    """Retriever de P2, según el contrato retrieve(question, k) -> list[RetrievedChunk].

    ``ruta`` tiene la forma «modulo:funcion»; si P2 la llama de otra forma basta con
    pasar --funcion-retrieve, sin tocar este fichero.
    """
    modulo, _, nombre = ruta.partition(":")
    try:
        funcion = getattr(importlib.import_module(modulo), nombre)
    except (ImportError, AttributeError) as exc:
        raise SystemExit(
            f"No existe {ruta} (pendiente de P2, contrato retrieve(question, k)). "
            "Usa --retriever bm25 mientras tanto."
        ) from exc
    return funcion


# ---------------------------------------------------------------------- salida
def _porcentaje(valor: float | None) -> str:
    return "  n/a" if valor is None else f"{valor * 100:5.1f}%"


def imprimir_resumen(m: dict) -> None:
    print(
        f"\nPreguntas: {m['n_preguntas']}  (con respuesta: {m['n_respondibles']}, "
        f"de rechazo: {m['n_rechazo']})  ·  k máx = {m['k_max']}"
        + (f"  ·  umbral = {m['umbral']}" if m["umbral"] is not None else "")
    )
    print("-" * 52)
    for k in KS:
        if f"hit_rate@{k}" in m:
            print(
                f"hit rate@{k:<2} (ficha + sección)   {_porcentaje(m[f'hit_rate@{k}'])}"
            )
    for k in KS:
        if f"acierto_medicamento@{k}" in m:
            print(
                f"acierto de ficha@{k:<2}            {_porcentaje(m[f'acierto_medicamento@{k}'])}"
            )
    print(
        f"MRR                            {m['mrr'] if m['mrr'] is not None else 'n/a'}"
    )
    print(f"acierto de sección@1           {_porcentaje(m['acierto_seccion@1'])}")
    print(f"rechazo correcto (lista vacía) {_porcentaje(m['rechazo_correcto'])}")
    print(f"falsos rechazos                {_porcentaje(m['falsos_rechazos'])}")
    print("\nHit rate por sección esperada:")
    clave_hit = f"hit@{m['k_max']}"
    for sec, d in m["por_seccion"].items():
        print(f"  {sec:<4} n={d['n']:<3} {_porcentaje(d[clave_hit])}")
    if m["fallos"]:
        print("\nPreguntas que fallan:", ", ".join(m["fallos"]))


def guardar(
    etiqueta: str,
    metricas: dict,
    resultados: list[ResultadoPregunta],
    barrido: list[dict] | None,
    carpeta: Path = RESULTADOS,
) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_json = carpeta / f"eval_retrieval_{etiqueta}.json"
    contenido = {"metricas": metricas}
    if barrido:
        contenido["barrido_umbral"] = barrido
        contenido["umbral_sugerido"] = mejor_umbral(barrido)
    ruta_json.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ruta_csv = carpeta / f"eval_retrieval_{etiqueta}_preguntas.csv"
    k_max = metricas["k_max"]
    with ruta_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "id",
                "categoria",
                "answerable",
                "esperado_nregistro",
                "esperado_seccion",
                "rango_acierto",
                "top1_nregistro",
                "top1_seccion",
                "top1_score",
                "n_recuperados",
                "pii_enmascarada",
                "pregunta",
            ]
        )
        for r in resultados:
            top = r.recuperados[0] if r.recuperados else (None, None, None)
            w.writerow(
                [
                    r.id,
                    r.categoria,
                    r.answerable,
                    r.expected_nregistro or "",
                    r.expected_seccion or "",
                    r.rango_acierto(k_max) or "",
                    top[0] or "",
                    top[1] or "",
                    "" if top[2] is None else round(top[2], 4),
                    len(r.recuperados),
                    r.enmascarada,
                    r.pregunta,
                ]
            )
    return [ruta_json, ruta_csv]


# ------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--retriever", choices=["real", "bm25"], default="real")
    p.add_argument("--golden", type=Path, default=GOLDEN_POR_DEFECTO)
    p.add_argument(
        "--chunks",
        type=Path,
        default=CHUNKS_POR_DEFECTO,
        help="chunks.jsonl (solo para --retriever bm25)",
    )
    p.add_argument(
        "--funcion-retrieve",
        default="src.retrieval.retriever:retrieve",
        help="'modulo:funcion' del retriever real (por defecto, el contrato)",
    )
    p.add_argument("--k", type=int, default=5)
    p.add_argument(
        "--umbral",
        type=float,
        default=None,
        help="descarta fragmentos con score menor (post-filtro)",
    )
    p.add_argument("--barrido-umbral", action="store_true")
    p.add_argument(
        "--sin-pii",
        action="store_true",
        help="no pasar las preguntas por el filtro PII",
    )
    p.add_argument("--etiqueta", default=None, help="nombre de los ficheros de salida")
    p.add_argument("--sin-guardar", action="store_true")
    args = p.parse_args(argv)

    golden = cargar_golden(args.golden)
    if args.retriever == "bm25":
        retriever = crear_retriever_bm25(cargar_chunks(args.chunks))
    else:
        retriever = cargar_retriever_real(args.funcion_retrieve)

    resultados = evaluar(golden, retriever, args.k, enmascarar_pii=not args.sin_pii)
    metricas = calcular_metricas(resultados, args.k, args.umbral)
    imprimir_resumen(metricas)

    barrido = None
    if args.barrido_umbral:
        barrido = barrido_umbral(resultados, args.k)
        print("\nBarrido de umbral:")
        print("umbral  hit@k   rechazo  falsos_rech  puntuación")
        for f in barrido:
            print(
                f"{f['umbral']:<7} {_porcentaje(f[f'hit_rate@{args.k}'])} "
                f"{_porcentaje(f['rechazo_correcto'])} {_porcentaje(f['falsos_rechazos'])}"
                f"   {f['puntuacion']}"
            )
        print("Umbral sugerido:", mejor_umbral(barrido)["umbral"])

    if not args.sin_guardar:
        etiqueta = args.etiqueta or args.retriever
        for ruta in guardar(etiqueta, metricas, resultados, barrido):
            print("Guardado:", ruta.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
