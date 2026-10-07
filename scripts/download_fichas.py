"""Descarga en data/raw/ el PDF de la ficha técnica de cada medicamento del catálogo.

Uso (desde la raíz del repo):
    python -m scripts.download_fichas
    python -m scripts.download_fichas --limite 5      # solo los 5 primeros (para pruebas)

Las fichas ya descargadas se saltan, así que se puede relanzar sin problema.

Responsable: P1
"""
import argparse
import logging
from pathlib import Path

from src.ingestion.catalogo import leer_catalogo
from src.ingestion.cima_client import CimaClient, CimaError, MedicamentoInfo

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalogo", type=Path, default=Path("data/catalogo_medicamentos.csv"))
    parser.add_argument("--destino", type=Path, default=Path("data/raw"))
    parser.add_argument("--limite", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    filas = leer_catalogo(args.catalogo)
    if not filas:
        raise SystemExit(f"No hay catálogo en {args.catalogo}. Ejecuta antes: python -m scripts.build_catalogo")
    if args.limite:
        filas = filas[: args.limite]

    cliente = CimaClient()
    ok, fallos = 0, []
    for i, fila in enumerate(filas, 1):
        info = MedicamentoInfo(
            nregistro=fila["nregistro"],
            nombre=fila["nombre"],
            principios_activos=fila["principios_activos"],
            atc=fila["atc"] or None,
            url_ficha_tecnica=fila["url_ficha_tecnica"] or None,
            ficha_segmentada=fila["ficha_segmentada"] == "1",
        )
        try:
            cliente.descargar_ficha_tecnica(info, args.destino)
            ok += 1
        except CimaError as e:
            fallos.append(info.nregistro)
            logger.error("[%d/%d] %s: %s", i, len(filas), info.nombre, e)

    print("\n===== RESUMEN =====")
    print(f"Fichas disponibles en {args.destino}: {ok}")
    print(f"Fallidas: {len(fallos)} {fallos if fallos else ''}")


if __name__ == "__main__":
    main()
