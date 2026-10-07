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
import unicodedata
from pathlib import Path

from src.ingestion.cima_client import (
    TIPO_FICHA_TECNICA,
    CimaClient,
    CimaError,
    MedicamentoInfo,
)

logger = logging.getLogger(__name__)

COLUMNAS = ["principio_activo_buscado", "nregistro", "nombre", "principios_activos",
            "atc", "url_ficha_tecnica", "ficha_segmentada"]


def _normaliza(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().strip().upper()


def _es_coincidencia_valida(pa_buscado: str, principios_activos_reales: str) -> bool:
    """CIMA filtra 'practiv1' por subcadena, no por coincidencia exacta: buscar "ibuprofeno"
    también devuelve medicamentos cuyo principio activo es "DEXIBUPROFENO" (lo contiene).
    "principios_activos_reales" viene como cadena ("PARACETAMOL" o "PARACETAMOL, CODEINA..."
    si es combinación).

    Comparamos por PALABRAS, no por subcadena: aceptamos si todas las palabras del buscado
    aparecen (como palabras completas) en el principio activo real, en cualquier orden. Así
    "naproxeno" -> "NAPROXENO SODICO" (sal) y "acetilsalicilico" -> "ACIDO ACETILSALICILICO"
    (con "ácido" delante) son válidos, pero "ibuprofeno" -> "DEXIBUPROFENO" no lo es: ahí
    "ibuprofeno" no es ninguna de las palabras de "DEXIBUPROFENO" (es una palabra distinta
    que lo contiene como subcadena, no como palabra suelta).
    """
    palabras_buscado = set(_normaliza(pa_buscado).split())
    if not palabras_buscado:
        return False
    for principio in (principios_activos_reales or "").split(","):
        palabras_reales = set(_normaliza(principio).split())
        if palabras_buscado <= palabras_reales:
            return True
    return False


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


def _con_ficha_tecnica(resultados: list[dict]) -> list[tuple[bool, dict]]:
    """(tiene_ficha_segmentada, resultado) de los que tienen ficha técnica."""
    con_ficha = []
    for r in resultados:
        ficha = next((d for d in r.get("docs") or [] if d.get("tipo") == TIPO_FICHA_TECNICA), None)
        if ficha and ficha.get("url"):
            con_ficha.append((bool(ficha.get("secc")), r))
    return con_ficha


def elegir_candidato(cliente: CimaClient, resultados: list[dict], pa_buscado: str,
                     max_candidatos: int = 60) -> MedicamentoInfo | None:
    """Elige el mejor medicamento de una búsqueda y devuelve su ficha de detalle.

    La búsqueda de CIMA (practiv1) filtra por subcadena, no por coincidencia exacta
    ("ibuprofeno" también trae "DEXIBUPROFENO"), y su respuesta NO incluye el principio
    activo real de cada resultado — eso solo está en el detalle de cada medicamento
    (GET /medicamento?nregistro=...). Así que hay que ir pidiendo el detalle candidato a
    candidato hasta encontrar uno cuyo principio activo es de verdad el buscado. Se
    comprueban primero los que CIMA tiene con ficha segmentada (para poder validar el
    chunker contra ellos), hasta un máximo de `max_candidatos` peticiones de detalle.
    """
    con_ficha = _con_ficha_tecnica(resultados)
    con_ficha.sort(key=lambda t: not t[0])  # segmentados primero
    for _, r in con_ficha[:max_candidatos]:
        try:
            info = cliente.obtener(str(r["nregistro"]))
        except CimaError:
            continue
        if _es_coincidencia_valida(pa_buscado, info.principios_activos):
            return info
    return None


def leer_catalogo(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    if filas and "principio_activo_buscado" not in filas[0]:
        raise ValueError(f"{ruta} tiene un formato antiguo: bórralo y vuelve a generarlo")
    # Ignora filas vacías o comentarios que no sean medicamentos
    return [f for f in filas if (f.get("nregistro") or "").strip().isdigit()]


def _buscar_exacto(cliente: CimaClient, pa: str, max_paginas: int = 10,
                   max_candidatos: int = 200) -> MedicamentoInfo | None:
    """Recorre páginas de resultados de CIMA (por si hubiera más de una) y comprueba, pidiendo
    el detalle de cada candidato con ficha técnica, hasta encontrar el principio activo exacto.
    """
    resultados: list[dict] = []
    for pagina in range(1, max_paginas + 1):
        pagina_resultados = cliente.buscar(principio_activo=pa, un_solo_principio_activo=True, pagina=pagina)
        if not pagina_resultados:
            break
        resultados.extend(pagina_resultados)
    return elegir_candidato(cliente, resultados, pa, max_candidatos=max_candidatos)


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
                info = _buscar_exacto(cliente, pa)
                if info is None:
                    resumen["sin_resultado"].append(pa)
                    logger.warning("[%d/%d] %s: sin medicamento con ficha técnica y principio activo exacto",
                                    i, len(principios), pa)
                    continue
                if str(info.nregistro) in nregistros:
                    resumen["ya_estaban"] += 1  # dos búsquedas que llevan al mismo medicamento
                    continue
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
