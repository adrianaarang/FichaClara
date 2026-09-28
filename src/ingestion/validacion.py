"""Validación del chunker: secciones detectadas frente a las oficiales de CIMA.

CIMA publica, para cada ficha técnica segmentada, la lista oficial de sus secciones
(GET docSegmentado/secciones/1?nregistro=...). La comparamos con lo que detecta
nuestro chunker en el PDF y calculamos:

- Cobertura (recall): de las secciones oficiales, cuántas hemos detectado.
- Precisión: de las que hemos detectado, cuántas existen de verdad.
- Cobertura en las secciones clave (4.1, 4.2, 4.3, 4.4, 4.5, 4.8), que son las que más
  se van a preguntar.

Solo se comparan los números de la plantilla oficial (1-10 y sus subapartados 4.x, 5.x,
6.x); los de tercer nivel (4.2.1) van dentro de su sección madre y no cuentan.
En las fichas EMA con varias presentaciones se compara solo la primera.

Uso:
    python -m src.ingestion.validacion              # todas las fichas de data/raw
    python -m src.ingestion.validacion --limite 10

Resultado: resumen en pantalla + docs/resultados/validacion_secciones.csv
Las respuestas de CIMA se guardan en data/processed/secciones_cima.json para no
volver a pedirlas.

Responsable: Adriana (P1)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.ingestion.chunker import PLANTILLA, detectar_secciones
from src.ingestion.cima_client import CimaClient, CimaError
from src.ingestion.cleaner import limpiar_documento
from src.ingestion.loaders import DocumentoIlegibleError, cargar_documento

logger = logging.getLogger(__name__)

CLAVE = ("4.1", "4.2", "4.3", "4.4", "4.5", "4.8")
CACHE = Path("data/processed/secciones_cima.json")
INFORME = Path("docs/resultados/validacion_secciones.csv")


@dataclass
class ResultadoFicha:
    nregistro: str
    oficiales: set[str]
    detectadas: set[str]
    faltan: set[str] = field(init=False)
    sobran: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.faltan = self.oficiales - self.detectadas
        self.sobran = self.detectadas - self.oficiales

    @property
    def aciertos(self) -> int:
        return len(self.oficiales & self.detectadas)


def normalizar_oficiales(secciones_cima: list[dict]) -> set[str]:
    """Números oficiales de CIMA que están en nuestra plantilla ('4.2', no '4.2.1')."""
    return {str(s.get("seccion", "")).strip().rstrip(".") for s in secciones_cima} & set(PLANTILLA)


def comparar(nregistro: str, oficiales: set[str], detectadas: set[str]) -> ResultadoFicha:
    return ResultadoFicha(nregistro, oficiales, detectadas & set(PLANTILLA))


def resumir(resultados: list[ResultadoFicha]) -> dict:
    oficiales = sum(len(r.oficiales) for r in resultados)
    detectadas = sum(len(r.detectadas) for r in resultados)
    aciertos = sum(r.aciertos for r in resultados)
    clave_oficiales = sum(len(r.oficiales & set(CLAVE)) for r in resultados)
    clave_aciertos = sum(len(r.oficiales & r.detectadas & set(CLAVE)) for r in resultados)
    return {
        "fichas": len(resultados),
        "cobertura": aciertos / oficiales if oficiales else 0.0,
        "precision": aciertos / detectadas if detectadas else 0.0,
        "cobertura_clave": clave_aciertos / clave_oficiales if clave_oficiales else 0.0,
        "fichas_perfectas": sum(not r.faltan and not r.sobran for r in resultados),
    }


def _secciones_detectadas(ruta: Path) -> set[str]:
    doc = limpiar_documento(cargar_documento(ruta))
    return {s.numero for s in detectar_secciones(doc) if s.producto == 1 and s.numero}


def _cargar_cache() -> dict[str, list[dict]]:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def validar_carpeta(carpeta: Path, cliente: CimaClient, limite: int | None = None) -> tuple[list[ResultadoFicha], list[str]]:
    cache = _cargar_cache()
    resultados, sin_datos = [], []
    archivos = sorted(carpeta.glob("FT_*.pdf"))[:limite]
    for n, ruta in enumerate(archivos, 1):
        print(f"[{n}/{len(archivos)}] {ruta.name}          ", end="\r", flush=True)
        nregistro = ruta.stem.removeprefix("FT_")
        if nregistro not in cache:
            try:
                cache[nregistro] = cliente.secciones_oficiales(nregistro)
            except CimaError as e:
                logger.warning("%s: %s", nregistro, e)
                continue
        oficiales = normalizar_oficiales(cache[nregistro])
        if not oficiales:
            sin_datos.append(nregistro)  # CIMA no tiene esta ficha segmentada
            continue
        try:
            detectadas = _secciones_detectadas(ruta)
        except DocumentoIlegibleError as e:
            logger.warning("%s: %s", ruta.name, e)
            continue
        resultados.append(comparar(nregistro, oficiales, detectadas))

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return resultados, sin_datos


def guardar_informe(resultados: list[ResultadoFicha], ruta: Path = INFORME) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nregistro", "oficiales", "detectadas", "aciertos", "faltan", "sobran"])
        for r in sorted(resultados, key=lambda r: (-len(r.faltan) - len(r.sobran), r.nregistro)):
            w.writerow([r.nregistro, len(r.oficiales), len(r.detectadas), r.aciertos,
                        " ".join(sorted(r.faltan)), " ".join(sorted(r.sobran))])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--carpeta", type=Path, default=Path("data/raw"))
    parser.add_argument("--limite", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    resultados, sin_datos = validar_carpeta(args.carpeta, CimaClient(), args.limite)
    guardar_informe(resultados)
    r = resumir(resultados)

    print("\n\n===== VALIDACIÓN DE SECCIONES CONTRA CIMA =====")
    print(f"Fichas comparadas:               {r['fichas']}  (sin datos segmentados en CIMA: {len(sin_datos)})")
    print(f"Cobertura (recall):              {r['cobertura']:.1%}")
    print(f"Precisión:                       {r['precision']:.1%}")
    print(f"Cobertura en secciones clave:    {r['cobertura_clave']:.1%}  {CLAVE}")
    print(f"Fichas con todas las secciones:  {r['fichas_perfectas']} de {r['fichas']}")
    peores = sorted(resultados, key=lambda x: -len(x.faltan) - len(x.sobran))[:5]
    if peores and (peores[0].faltan or peores[0].sobran):
        print("Fichas con más diferencias:")
        for x in peores:
            if x.faltan or x.sobran:
                print(f"   FT_{x.nregistro}: faltan {sorted(x.faltan) or '-'} · sobran {sorted(x.sobran) or '-'}")
    print(f"Informe completo: {INFORME}")


if __name__ == "__main__":
    main()
