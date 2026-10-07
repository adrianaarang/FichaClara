"""Crea data/catalogo_medicamentos.csv buscando cada principio activo en CIMA.

Uso (desde la raíz del repo):
    python -m scripts.build_catalogo                 # lista curada data/principios_activos.txt
    python -m scripts.build_catalogo --todos         # TODOS los principios activos de CIMA (tarda ~1 h)
    python -m scripts.build_catalogo --todos --limite 500

Es reanudable: si se corta, vuelve a lanzarlo y continúa donde lo dejó.

Responsable: P1
"""
import argparse
import logging
from pathlib import Path

from src.ingestion.catalogo import construir_catalogo, leer_lista
from src.ingestion.cima_client import CimaClient

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lista", type=Path, default=Path("data/principios_activos.txt"))
    parser.add_argument("--salida", type=Path, default=Path("data/catalogo_medicamentos.csv"))
    parser.add_argument("--todos", action="store_true", help="usar la maestra completa de CIMA")
    parser.add_argument("--limite", type=int, default=None, help="máximo de principios activos a procesar")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cliente = CimaClient()

    if args.todos:
        principios = cliente.principios_activos()
        logger.info("La maestra de CIMA tiene %d principios activos", len(principios))
    else:
        principios = leer_lista(args.lista)
    if args.limite:
        principios = principios[: args.limite]

    resumen = construir_catalogo(principios, cliente, args.salida)

    print("\n===== RESUMEN =====")
    print(f"Añadidos:        {resumen['añadidos']}")
    print(f"Ya estaban:      {resumen['ya_estaban']}")
    print(f"Sin resultado:   {len(resumen['sin_resultado'])}")
    if resumen["sin_resultado"] and not args.todos:
        print("   " + ", ".join(resumen["sin_resultado"]))
    print(f"Errores de red:  {len(resumen['errores'])} (relanza el script para reintentarlos)")
    print(f"Catálogo en:     {args.salida}")


if __name__ == "__main__":
    main()
