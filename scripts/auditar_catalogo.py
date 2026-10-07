"""Audita catalogo_medicamentos.csv: filas donde el principio activo buscado NO es una
coincidencia exacta con el principio activo real del medicamento elegido.

Motivo: CIMA filtra por "practiv1" con coincidencia de subcadena, no exacta. Buscar
"ibuprofeno" también devuelve medicamentos cuyo principio activo es "DEXIBUPROFENO"
(la contiene). elegir_candidato() no comprobaba esto, así que algunas filas del catálogo
apuntan al medicamento equivocado — el caso más grave: "morfina" quedó asociado a
"APOMORFINA", un fármaco sin relación clínica (agonista dopaminérgico, no un opioide).

No modifica el CSV, solo informa. Revisar cada fila señalada a mano y decidir: si CIMA
tiene el principio activo exacto con ficha técnica, sustituir la fila; si no lo tiene
comercializado en solitario, decidir si se descarta ese principio activo del catálogo.

Uso:
    python -m scripts.auditar_catalogo
"""
from __future__ import annotations

import csv
import unicodedata
from pathlib import Path

CATALOGO = Path("data/catalogo_medicamentos.csv")


def _normaliza(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().strip().upper()


def principios_de(campo: str) -> list[str]:
    """'IBUPROFENO' o 'PARACETAMOL, CODEINA FOSFATO HEMIHIDRATO' -> lista normalizada."""
    return [_normaliza(p) for p in campo.split(",") if p.strip()]


def es_coincidencia_valida(buscado: str, reales: list[str]) -> bool:
    """Exacta, o el real es 'BUSCADO + sal' ('NAPROXENO' -> 'NAPROXENO SODICO').

    No vale que el buscado esté sepultado dentro de otra palabra ('IBUPROFENO' dentro de
    'DEXIBUPROFENO'): eso es el bug de coincidencia por subcadena de CIMA (practiv1), no
    una variante farmacéutica normal.
    """
    return any(r == buscado or r.startswith(buscado + " ") for r in reales)


def auditar(ruta: Path = CATALOGO) -> list[dict]:
    sospechosas = []
    with ruta.open(encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            buscado = _normaliza(fila.get("principio_activo_buscado", ""))
            reales = principios_de(fila.get("principios_activos", ""))
            if buscado and not es_coincidencia_valida(buscado, reales):
                sospechosas.append(fila)
    return sospechosas


def main() -> None:
    sospechosas = auditar()
    print(f"===== AUDITORÍA DEL CATÁLOGO: {CATALOGO} =====")
    print(f"Filas donde el principio activo buscado no coincide exactamente: "
          f"{len(sospechosas)}\n")
    for fila in sospechosas:
        print(f"  buscado: {fila['principio_activo_buscado']:<20} → "
              f"nregistro {fila['nregistro']}: {fila['nombre']} "
              f"(principios reales: {fila['principios_activos']})")
    if not sospechosas:
        print("  Nada que revisar.")


if __name__ == "__main__":
    main()
