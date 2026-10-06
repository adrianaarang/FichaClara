"""Tests for medication detection in user queries."""

from pathlib import Path

import pytest

from src.retrieval.query_parser import (
    detect_medication,
    find_medications,
    normalize_text,
)

CATALOG_CONTENT = """principio_activo_buscado,nregistro,nombre,principios_activos
omeprazol,64004,GASTROMEL 20 MG CAPSULAS DURAS GASTRORRESISTENTES EFG,OMEPRAZOL
morfina,83323,DROPIZOL 10 MG/ML GOTAS ORALES EN SOLUCION,MORFINA
sitagliptina,07383014,JANUVIA 100 MG COMPRIMIDOS RECUBIERTOS CON PELICULA,SITAGLIPTINA FOSFATO MONOHIDRATO
loratadina,58518,CLARITYNE 10 mg COMPRIMIDOS,LORATADINA
desloratadina,00160065,AERIUS 5 MG COMPRIMIDOS RECUBIERTOS CON PELICULA,DESLORATADINA
"""


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    """Create a small deterministic medication catalogue."""
    path = tmp_path / "catalog.csv"
    path.write_text(CATALOG_CONTENT, encoding="utf-8")
    return path


def test_normalize_text_ignores_case_accents_and_punctuation() -> None:
    assert normalize_text("Ácido Fólico, 5 MG") == "acido folico 5 mg"


def test_detects_searched_active_ingredient(catalog_path: Path) -> None:
    result = detect_medication(
        "¿Qué contraindicaciones tiene el omeprazol?",
        catalog_path,
    )

    assert result is not None
    assert result.registration_number == "64004"
    assert result.matched_alias == "omeprazol"
    assert result.match_type == "searched_active_ingredient"


def test_detects_commercial_name(catalog_path: Path) -> None:
    result = detect_medication(
        "¿Para qué está indicado Januvia?",
        catalog_path,
    )

    assert result is not None
    assert result.registration_number == "07383014"
    assert result.matched_alias == "januvia"
    assert result.match_type == "commercial_name"


def test_detects_official_active_ingredient(catalog_path: Path) -> None:
    result = detect_medication(
        "Información sobre sitagliptina fosfato monohidrato",
        catalog_path,
    )

    assert result is not None
    assert result.registration_number == "07383014"
    assert result.match_type == "official_active_ingredient"


def test_does_not_match_inside_another_word(catalog_path: Path) -> None:
    result = detect_medication(
        "¿Qué información hay sobre la apomorfina?",
        catalog_path,
    )

    assert result is None


def test_returns_none_when_no_medication_is_detected(catalog_path: Path) -> None:
    result = detect_medication(
        "¿Cuál es la política de vacaciones de la empresa?",
        catalog_path,
    )

    assert result is None


def test_returns_none_when_question_mentions_multiple_medications(
    catalog_path: Path,
) -> None:
    result = detect_medication(
        "Compara loratadina con desloratadina",
        catalog_path,
    )

    assert result is None


def test_missing_catalog_raises_file_not_found(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="Medication catalogue not found"):
        detect_medication("omeprazol", missing_path)


def test_find_medications_returns_multiple_known_medications(
    catalog_path: Path,
) -> None:
    results = find_medications(
        "Compara loratadina con desloratadina",
        catalog_path,
    )

    assert {result.registration_number for result in results} == {
        "58518",
        "00160065",
    }


def test_find_medications_returns_empty_when_none_are_known(
    catalog_path: Path,
) -> None:
    assert find_medications("¿Cuál es la capital de Francia?", catalog_path) == ()
