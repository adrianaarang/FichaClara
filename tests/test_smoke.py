"""Test mínimo para que la CI tenga algo que ejecutar desde el primer día.

Responsable: P5. Se puede borrar cuando cada módulo tenga sus propios tests.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_estructura_basica_del_repo():
    for ruta in ["src", "frontend", "tests", "requirements.txt", "README.md"]:
        assert (RAIZ / ruta).exists(), f"Falta {ruta}"
