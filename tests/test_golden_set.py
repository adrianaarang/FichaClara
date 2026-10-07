"""Integridad del golden set: formato, reparto y coherencia con el catálogo.

Responsable: P5 · Calidad, evaluación, DevOps y documentación
"""

import csv
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
GOLDEN = RAIZ / "evaluation" / "golden_set.jsonl"
CATALOGO = RAIZ / "data" / "catalogo_medicamentos.csv"

CATEGORIAS = {
    "con_respuesta",
    "con_respuesta_con_pii",
    "medicamento_ausente",
    "fuera_de_alcance",
    "consejo_clinico",
    "prompt_injection",
}
SECCIONES_FICHA = {
    "1", "2", "3", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9",
    "5.1", "5.2", "5.3", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "7", "8", "9", "10",
}  # fmt: skip


@pytest.fixture(scope="module")
def golden():
    with GOLDEN.open(encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


@pytest.fixture(scope="module")
def catalogo():
    with CATALOGO.open(encoding="utf-8") as f:
        return {r["nregistro"]: r for r in csv.DictReader(f)}


def test_tamano_y_reparto(golden):
    assert 35 <= len(golden) <= 50
    con = [g for g in golden if g["answerable"]]
    sin = [g for g in golden if not g["answerable"]]
    assert len(con) >= 25
    assert len(sin) >= 8


def test_ids_unicos_y_campos_obligatorios(golden):
    ids = [g["id"] for g in golden]
    assert len(ids) == len(set(ids))
    for g in golden:
        for campo in ("id", "question", "answerable", "categoria"):
            assert campo in g, f"{g.get('id')}: falta {campo}"
        assert len(g["question"]) >= 3


def test_categorias_validas(golden):
    for g in golden:
        assert g["categoria"] in CATEGORIAS, g["id"]


def test_coherencia_answerable_y_esperados(golden):
    for g in golden:
        if g["answerable"]:
            assert g["expected_nregistro"], g["id"]
            assert g["expected_seccion"] in SECCIONES_FICHA, g["id"]
            assert g["categoria"] in {"con_respuesta", "con_respuesta_con_pii"}
        else:
            assert g["expected_nregistro"] is None, g["id"]
            assert g["expected_seccion"] is None, g["id"]


def test_los_nregistro_existen_en_el_catalogo(golden, catalogo):
    for g in golden:
        if g["answerable"]:
            assert isinstance(g["expected_nregistro"], str)
            assert g["expected_nregistro"] in catalogo, g["id"]


def test_las_preguntas_con_pii_estan_marcadas(golden):
    from src.guardrails.pii_filter import check_pii

    for g in golden:
        detectada = check_pii(g["question"]).contiene_pii
        assert detectada == bool(g.get("expected_pii", False)), g["id"]


def test_cobertura_de_secciones_clave(golden):
    secciones = {g["expected_seccion"] for g in golden if g["answerable"]}
    assert {"4.1", "4.2", "4.3", "4.4", "4.5", "4.8", "4.9"} <= secciones


def test_hay_casos_de_cada_tipo_de_rechazo(golden):
    categorias = {g["categoria"] for g in golden if not g["answerable"]}
    assert {
        "medicamento_ausente",
        "fuera_de_alcance",
        "consejo_clinico",
        "prompt_injection",
    } <= categorias


def test_medicamentos_ausentes_no_estan_en_el_catalogo(golden, catalogo):
    """Si alguien añade sildenafilo al catálogo, esta pregunta deja de ser 'sin respuesta'."""
    activos = " ".join(r["principios_activos"].lower() for r in catalogo.values())
    for g in golden:
        if g["categoria"] == "medicamento_ausente":
            for candidato in ("sildenafilo", "tacrolimus", "ivermectina"):
                if candidato in g["question"].lower():
                    assert candidato not in activos, g["id"]
