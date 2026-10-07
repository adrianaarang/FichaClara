"""Diagnóstico: qué devuelve CIMA de verdad al buscar un principio activo, página a página.

No toca el catálogo ni ningún archivo. Solo para ver por qué un principio activo no
encuentra coincidencia exacta con _buscar_exacto (catalogo.py).

Uso:
    python -m scripts.diagnostico_busqueda ibuprofeno
    python -m scripts.diagnostico_busqueda ibuprofeno --paginas 15
"""
from __future__ import annotations

import argparse

from src.ingestion.cima_client import CimaClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("principio_activo")
    parser.add_argument("--paginas", type=int, default=10)
    parser.add_argument("--detalle", type=int, default=0,
                        help="pide el detalle real (principio activo de verdad) de los "
                             "primeros N candidatos con ficha técnica. Tarda más (una "
                             "petición extra a CIMA por candidato).")
    parser.add_argument("--todos-comercializados", action="store_true",
                        help="incluye también los medicamentos ya no comercializados")
    args = parser.parse_args()

    cliente = CimaClient()
    total_visto = 0
    pedidos = 0
    for pagina in range(1, args.paginas + 1):
        resultados = cliente.buscar(principio_activo=args.principio_activo,
                                     un_solo_principio_activo=True, pagina=pagina,
                                     solo_comercializados=not args.todos_comercializados)
        print(f"\n--- página {pagina}: {len(resultados)} resultados ---")
        if not resultados:
            print("  (vacío, no hay más páginas)")
            break
        total_visto += len(resultados)
        for r in resultados:
            con_ficha = any(d.get("tipo") == 1 for d in r.get("docs") or [])
            if args.detalle and con_ficha and pedidos < args.detalle:
                info = cliente.obtener(str(r["nregistro"]))
                pedidos += 1
                print(f"  nregistro={r.get('nregistro'):<14} PRINCIPIO ACTIVO REAL="
                      f"{info.principios_activos!r:<45} nombre={info.nombre}")
            else:
                print(f"  nregistro={r.get('nregistro'):<14} con_ficha_tecnica={con_ficha}")

    print(f"\nTotal de resultados vistos en {args.paginas} páginas: {total_visto}")
    if args.detalle:
        print(f"Detalle pedido de {pedidos} candidatos (de los primeros con ficha técnica).")


if __name__ == "__main__":
    main()
