"""Tests de la validación de secciones contra CIMA (sin conexión).

Responsable: Adriana (P1)
"""
import shutil
from pathlib import Path

import src.ingestion.validacion as val
from src.ingestion.validacion import (
    comparar,
    normalizar_oficiales,
    resumir,
    validar_carpeta,
)

FIXTURES = Path(__file__).parent / "fixtures"
OFICIALES_ACFOL = ["1", "2", "3", "4", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9",
                   "5", "5.1", "5.2", "5.3", "6", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "7", "8", "9", "10"]


def test_normalizar_quita_tercer_nivel():
    cima = [{"seccion": "4.2"}, {"seccion": "4.2.1"}, {"seccion": "4.2.2"}, {"seccion": "10"}]
    assert normalizar_oficiales(cima) == {"4.2", "10"}


def test_comparar_y_resumir():
    r1 = comparar("1", {"4.1", "4.2", "4.5"}, {"4.1", "4.2", "4.5"})
    r2 = comparar("2", {"4.1", "4.2", "4.5", "4.8"}, {"4.1", "4.2", "6.1"})
    assert r2.faltan == {"4.5", "4.8"} and r2.sobran == {"6.1"}
    res = resumir([r1, r2])
    assert res["fichas_perfectas"] == 1
    assert round(res["cobertura"], 3) == round(5 / 7, 3)
    assert round(res["precision"], 3) == round(5 / 6, 3)


class ClienteFalso:
    def secciones_oficiales(self, nregistro):
        return [{"seccion": s} for s in OFICIALES_ACFOL] if nregistro == "11265" else []


def test_validar_ficha_real(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(val, "CACHE", tmp_path / "cache.json")
    shutil.copy(FIXTURES / "FT_11265.pdf", tmp_path)
    resultados, sin_datos = validar_carpeta(tmp_path, ClienteFalso())
    assert sin_datos == [] and len(resultados) == 1
    r = resultados[0]
    assert {"4.1", "4.2", "4.3", "4.5", "4.8"} <= r.detectadas
    assert not r.sobran                   # no inventa secciones
    assert resumir(resultados)["cobertura"] >= 0.9
