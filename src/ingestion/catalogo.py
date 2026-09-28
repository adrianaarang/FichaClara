"""Construcción del catálogo de medicamentos a indexar.

Para cada principio activo busca en CIMA un medicamento comercializado que lo contenga
SOLO (sin combinaciones) y que tenga ficha técnica, y lo guarda en
data/catalogo_medicamentos.csv. Es reanudable: si se corta, al relanzarlo se salta
los principios activos que ya están en el CSV.

Responsable: P1 · Ingesta y chunking
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from src.ingestion.cima_client import TIPO_FICHA_TECNICA, CimaClient, CimaError

logger = logging.getLogger(__name__)

COLUMNAS = ["principio_activo_buscado", "nregistro", "nombre", "principios_activos",
            "atc", "url_ficha_tecnica", "ficha_segmentada"]


def leer_lista(ruta: Path) -> list[str]:
    """Lee un .txt con un principio activo por línea (ignora vacías y comentarios #)."""
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    vistos, lista = set(), []
    for linea in lineas:
        pa = linea.strip()
        if pa and not pa.startswith("#") and pa.lower() not in vistos:
            vistos.add(pa.lower())
            lista.append(pa)
    return lista


def elegir_candidato(resultados: list[dict]) -> dict | None:
    """Elige el mejor medicamento de una búsqueda.

    Solo vale si tiene ficha técnica. Preferimos los que CIMA tiene segmentados por
    secciones (así podremos validar el chunker contra ellos).
    """
    con_ficha = []
    for r in resultados:
        ficha = next((d for d in r.get("docs") or [] if d.get("tipo") == TIPO_FICHA_TECNICA), None)
        if ficha and ficha.get("url"):
            con_ficha.append((bool(ficha.get("secc")), r))
    if not con_ficha:
        return None
    segmentados = [r for secc, r in con_ficha if secc]
    return segmentados[0] if segmentados else con_ficha[0][1]


def leer_catalogo(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    if filas and "principio_activo_buscado" not in filas[0]:
        raise ValueError(f"{ruta} tiene un formato antiguo: bórralo y vuelve a generarlo")
    # Ignora filas vacías o comentarios que no sean medicamentos
    return [f for f in filas if (f.get("nregistro") or "").strip().isdigit()]


def construir_catalogo(principios: list[str], cliente: CimaClient, ruta_csv: Path) -> dict:
    """Busca cada principio activo y va añadiendo filas al CSV. Devuelve un resumen."""
    ya_hechos = {fila["principio_activo_buscado"].lower() for fila in leer_catalogo(ruta_csv)}
    nregistros = {fila["nregistro"] for fila in leer_catalogo(ruta_csv)}
    nuevo = not ruta_csv.exists()
    ruta_csv.parent.mkdir(parents=True, exist_ok=True)

    resumen = {"añadidos": 0, "ya_estaban": 0, "sin_resultado": [], "errores": []}
    with ruta_csv.open("a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        if nuevo:
            escritor.writeheader()

        for i, pa in enumerate(principios, 1):
            if pa.lower() in ya_hechos:
                resumen["ya_estaban"] += 1
                continue
            try:
                resultados = cliente.buscar(principio_activo=pa, un_solo_principio_activo=True)
                elegido = elegir_candidato(resultados)
                if elegido is None:
                    resumen["sin_resultado"].append(pa)
                    logger.warning("[%d/%d] %s: sin medicamento con ficha técnica", i, len(principios), pa)
                    continue
                if str(elegido["nregistro"]) in nregistros:
                    resumen["ya_estaban"] += 1  # dos búsquedas que llevan al mismo medicamento
                    continue
                info = cliente.obtener(str(elegido["nregistro"]))
            except CimaError as e:
                resumen["errores"].append(pa)
                logger.error("[%d/%d] %s: %s", i, len(principios), pa, e)
                continue

            escritor.writerow({
                "principio_activo_buscado": pa,
                "nregistro": info.nregistro,
                "nombre": info.nombre,
                "principios_activos": info.principios_activos,
                "atc": info.atc or "",
                "url_ficha_tecnica": info.url_ficha_tecnica or "",
                "ficha_segmentada": int(info.ficha_segmentada),
            })
            f.flush()  # si se corta, lo escrito no se pierde
            nregistros.add(info.nregistro)
            resumen["añadidos"] += 1
            logger.info("[%d/%d] %s → %s", i, len(principios), pa, info.nombre)
    return resumen
