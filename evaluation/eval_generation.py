"""Fidelidad, cita correcta y rechazo de preguntas sin respuesta.

Responsable: P5 · Calidad, evaluación, DevOps y documentación

Lanza cada pregunta del golden set contra POST /query (API de P3) y comprueba, con el
contrato QueryResponse de src/common/schemas.py:

    rechazo_correcto     medicamento ausente / fuera de alcance -> encontrado=False
    falsos_rechazos      pregunta con respuesta -> encontrado=False (mal)
    citas_validas        todo [n] del texto apunta a una fuente que existe (objetivo 100 %)
    con_citas            las respuestas encontradas citan al menos una fuente
    cita_correcta        una fuente CITADA es la ficha y sección esperadas
    fuente_recuperada    alguna fuente (citada o no) es la ficha y sección esperadas
    aviso_pii_correcto   aviso_pii coincide con expected_pii (y no salta sin PII)
    sin_fuga             la respuesta no contiene las frases de «no_debe_contener»

La fidelidad (que lo afirmado esté realmente en los fragmentos) no se puede decidir
con reglas: el script genera docs/resultados/revision_fidelidad.csv para revisarla a
mano (columna «fiel»: sí / no / parcial). Las categorías consejo_clinico y
prompt_injection también van a esa hoja.

Uso:
    uvicorn src.api.main:app            # en otra terminal
    python -m evaluation.eval_generation --api-url http://localhost:8000
    python -m evaluation.eval_generation --etiqueta groq-llama33

Salida: tabla en pantalla + docs/resultados/eval_generation_<etiqueta>.json,
..._preguntas.csv y revision_fidelidad.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from evaluation.eval_retrieval import (
    CATEGORIAS_RECHAZO,
    GOLDEN_POR_DEFECTO,
    cargar_golden,
)
from src.common.schemas import QueryResponse

RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "docs" / "resultados"

_RE_CITA = re.compile(r"\[(\d+)\]")

Consulta = Callable[[str], dict]


def consultar_api(api_url: str, timeout: float = 60.0) -> Consulta:
    """Consulta = función pregunta -> JSON de POST /query."""
    import httpx

    def consulta(pregunta: str) -> dict:
        r = httpx.post(
            f"{api_url.rstrip('/')}/query", json={"pregunta": pregunta}, timeout=timeout
        )
        r.raise_for_status()
        return r.json()

    return consulta


def _porcentaje(aciertos: int, total: int) -> float | None:
    return round(aciertos / total, 4) if total else None


def evaluar_pregunta(g: dict, consulta: Consulta) -> dict:
    """Evalúa una pregunta del golden set. Nunca lanza: los fallos quedan en 'error'."""
    fila: dict = {
        "id": g["id"],
        "categoria": g.get("categoria", ""),
        "pregunta": g["question"],
        "answerable": bool(g["answerable"]),
        "esperado_nregistro": g.get("expected_nregistro"),
        "esperado_seccion": g.get("expected_seccion"),
        "error": None,
    }
    try:
        resp = QueryResponse.model_validate(consulta(g["question"]))
    except (ValidationError, ValueError) as exc:
        fila["error"] = f"respuesta fuera de contrato: {exc}"[:300]
        return fila
    except Exception as exc:  # noqa: BLE001 - red, timeout, 5xx: se anota y se sigue
        fila["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return fila

    citas = [int(n) for n in _RE_CITA.findall(resp.respuesta)]
    indices = {f.indice for f in resp.fuentes}
    esperado_doc = (
        f"FT_{g['expected_nregistro']}" if g.get("expected_nregistro") else None
    )

    def coincide(f) -> bool:
        return f.doc_id == esperado_doc and f.seccion == g.get("expected_seccion")

    fila.update(
        {
            "encontrado": resp.encontrado,
            "aviso_pii": resp.aviso_pii,
            "modelo": resp.modelo,
            "n_fuentes": len(resp.fuentes),
            "n_citas": len(citas),
            "citas_validas": all(c in indices for c in citas),
            "con_citas": bool(citas),
            "fuente_recuperada": any(coincide(f) for f in resp.fuentes),
            "cita_correcta": any(
                coincide(f) for f in resp.fuentes if f.indice in citas
            ),
            "aviso_pii_correcto": resp.aviso_pii == bool(g.get("expected_pii", False)),
            "sin_fuga": not any(
                frase.lower() in resp.respuesta.lower()
                for frase in g.get("no_debe_contener", [])
            ),
            "respuesta": resp.respuesta,
            "fuentes_resumen": [
                f"[{f.indice}] {f.nombre} · {f.seccion} · p.{f.pagina}: "
                f"{f.fragmento[:200]}"
                for f in resp.fuentes
            ],
        }
    )
    return fila


def calcular_metricas(filas: list[dict]) -> dict:
    ok = [f for f in filas if not f["error"]]
    respondibles = [f for f in ok if f["answerable"]]
    de_rechazo = [f for f in ok if f["categoria"] in CATEGORIAS_RECHAZO]
    encontradas = [f for f in ok if f["encontrado"]]
    con_pii = [f for f in ok if f["categoria"] == "con_respuesta_con_pii"]
    sin_pii = [f for f in ok if f["categoria"] != "con_respuesta_con_pii"]
    con_frase_prohibida = [
        f for f in ok if "sin_fuga" in f and f["sin_fuga"] is not None
    ]

    return {
        "n_preguntas": len(filas),
        "n_errores": len(filas) - len(ok),
        "rechazo_correcto": _porcentaje(
            sum(not f["encontrado"] for f in de_rechazo), len(de_rechazo)
        ),
        "falsos_rechazos": _porcentaje(
            sum(not f["encontrado"] for f in respondibles), len(respondibles)
        ),
        "citas_validas": _porcentaje(
            sum(f["citas_validas"] for f in encontradas), len(encontradas)
        ),
        "con_citas": _porcentaje(
            sum(f["con_citas"] for f in encontradas), len(encontradas)
        ),
        "cita_correcta": _porcentaje(
            sum(f["cita_correcta"] for f in respondibles), len(respondibles)
        ),
        "fuente_recuperada": _porcentaje(
            sum(f["fuente_recuperada"] for f in respondibles), len(respondibles)
        ),
        "aviso_pii_correcto_con_pii": _porcentaje(
            sum(f["aviso_pii"] for f in con_pii), len(con_pii)
        ),
        "falsas_alarmas_pii": _porcentaje(
            sum(f["aviso_pii"] for f in sin_pii), len(sin_pii)
        ),
        "sin_fuga": _porcentaje(
            sum(f["sin_fuga"] for f in con_frase_prohibida), len(con_frase_prohibida)
        ),
        "ids_con_error": [f["id"] for f in filas if f["error"]],
        "ids_cita_invalida": [f["id"] for f in encontradas if not f["citas_validas"]],
        "ids_fuga": [f["id"] for f in ok if not f["sin_fuga"]],
    }


def hoja_revision(filas: list[dict], golden: list[dict]) -> list[dict]:
    """Filas para revisar a mano: fidelidad de lo respondido y casos delicados."""
    manual = {g["id"] for g in golden if g.get("revision_manual")}
    hoja = []
    for f in filas:
        if f["error"] or not (
            (f["answerable"] and f["encontrado"]) or f["id"] in manual
        ):
            continue
        hoja.append(
            {
                "id": f["id"],
                "categoria": f["categoria"],
                "pregunta": f["pregunta"],
                "encontrado": f["encontrado"],
                "respuesta": f["respuesta"],
                "fuentes": " || ".join(f["fuentes_resumen"]),
                "fiel (si/no/parcial)": "",
                "comentario": "",
            }
        )
    return hoja


def _escribir_csv(ruta: Path, filas: list[dict]) -> None:
    if not filas:
        return
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow(
                {
                    k: (" || ".join(v) if isinstance(v, list) else v)
                    for k, v in fila.items()
                }
            )


def guardar(
    etiqueta: str,
    metricas: dict,
    filas: list[dict],
    golden: list[dict],
    carpeta: Path = RESULTADOS,
) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_json = carpeta / f"eval_generation_{etiqueta}.json"
    ruta_json.write_text(
        json.dumps({"metricas": metricas}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ruta_csv = carpeta / f"eval_generation_{etiqueta}_preguntas.csv"
    _escribir_csv(ruta_csv, filas)
    ruta_rev = carpeta / "revision_fidelidad.csv"
    _escribir_csv(ruta_rev, hoja_revision(filas, golden))
    return [ruta_json, ruta_csv, ruta_rev]


def _pct(v: float | None) -> str:
    return "  n/a" if v is None else f"{v * 100:5.1f}%"


def imprimir_resumen(m: dict) -> None:
    print(f"\nPreguntas: {m['n_preguntas']}  ·  errores de llamada: {m['n_errores']}")
    print("-" * 52)
    filas = [
        ("rechazo correcto (found=false)", "rechazo_correcto"),
        ("falsos rechazos", "falsos_rechazos"),
        ("citas válidas (objetivo 100 %)", "citas_validas"),
        ("respuestas con cita", "con_citas"),
        ("cita correcta (ficha + sección)", "cita_correcta"),
        ("fuente correcta recuperada", "fuente_recuperada"),
        ("aviso PII cuando hay PII", "aviso_pii_correcto_con_pii"),
        ("falsas alarmas de PII", "falsas_alarmas_pii"),
        ("sin fuga / frases prohibidas", "sin_fuga"),
    ]
    for etiqueta, clave in filas:
        print(f"{etiqueta:<34}{_pct(m[clave])}")
    for clave, texto in [
        ("ids_con_error", "Con error"),
        ("ids_cita_invalida", "Citas inválidas"),
        ("ids_fuga", "Fuga / frase prohibida"),
    ]:
        if m[clave]:
            print(f"{texto}: {', '.join(m[clave])}")
    print("\nRevisa a mano docs/resultados/revision_fidelidad.csv (columna «fiel»).")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--api-url", default="http://localhost:8000")
    p.add_argument("--golden", type=Path, default=GOLDEN_POR_DEFECTO)
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--etiqueta", default="api")
    p.add_argument("--sin-guardar", action="store_true")
    args = p.parse_args(argv)

    golden = cargar_golden(args.golden)
    consulta = consultar_api(args.api_url, args.timeout)
    filas = [evaluar_pregunta(g, consulta) for g in golden]
    metricas = calcular_metricas(filas)
    imprimir_resumen(metricas)
    if not args.sin_guardar:
        for ruta in guardar(args.etiqueta, metricas, filas, golden):
            print("Guardado:", ruta.relative_to(RAIZ))
    return 0 if not metricas["n_errores"] else 1


if __name__ == "__main__":
    sys.exit(main())
