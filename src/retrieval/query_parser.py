"""Detect medications mentioned in user questions.

The query parser maps commercial names and active ingredients from the
FichaClara catalogue to their registration number so retrieval can be
restricted to the correct technical sheet.

Responsible: P2 · Embeddings, vector database and retrieval.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

DEFAULT_CATALOG_PATH = Path("data/catalogo_medicamentos.csv")

MatchType = Literal[
    "searched_active_ingredient",
    "official_active_ingredient",
    "commercial_name",
]


@dataclass(frozen=True, slots=True)
class MedicationMatch:
    """Medication detected in a user question."""

    registration_number: str
    name: str
    active_ingredients: str
    matched_alias: str
    match_type: MatchType


@dataclass(frozen=True, slots=True)
class _CatalogEntry:
    registration_number: str
    name: str
    searched_active_ingredient: str
    active_ingredients: str


def normalize_text(text: str) -> str:
    """Normalize text for accent- and case-insensitive matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    alphanumeric = re.sub(r"[^a-z0-9]+", " ", without_accents.casefold())
    return " ".join(alphanumeric.split())


def _commercial_name_alias(name: str) -> str:
    """Extract the useful commercial-name prefix before the dosage.

    Example:
        "JANUVIA 100 MG COMPRIMIDOS" -> "januvia"
        "DIFENADOL RAPID 400 mg ..." -> "difenadol rapid"
    """
    normalized = normalize_text(name)
    tokens = normalized.split()

    prefix: list[str] = []
    for token in tokens:
        if any(char.isdigit() for char in token):
            break
        prefix.append(token)

    return " ".join(prefix) or normalized


def _contains_phrase(text: str, phrase: str) -> bool:
    """Return True only when phrase appears on complete word boundaries."""
    if not phrase:
        return False

    return f" {phrase} " in f" {text} "


@lru_cache(maxsize=8)
def _load_catalog(path: str) -> tuple[_CatalogEntry, ...]:
    """Load and cache medication records from the CSV catalogue."""
    catalog_path = Path(path)

    if not catalog_path.is_file():
        raise FileNotFoundError(f"Medication catalogue not found: {catalog_path}")

    with catalog_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        required_columns = {
            "nregistro",
            "nombre",
            "principio_activo_buscado",
            "principios_activos",
        }
        missing_columns = required_columns - set(reader.fieldnames or [])

        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Medication catalogue is missing columns: {missing}")

        entries = [
            _CatalogEntry(
                registration_number=row["nregistro"].strip(),
                name=row["nombre"].strip(),
                searched_active_ingredient=row["principio_activo_buscado"].strip(),
                active_ingredients=row["principios_activos"].strip(),
            )
            for row in reader
            if row["nregistro"].strip()
        ]

    return tuple(entries)


def detect_medication(
    question: str,
    catalog_path: str | Path = DEFAULT_CATALOG_PATH,
) -> MedicationMatch | None:
    """Detect one unambiguous medication mentioned in a question.

    Matching considers:
    - the active ingredient used to build the catalogue;
    - the official active ingredient reported by CIMA;
    - the commercial medication name.

    Matching is performed on complete words after normalizing case and
    accents. If no medication is found, or more than one medication is
    detected, ``None`` is returned so retrieval does not apply an unsafe
    metadata filter.
    """
    normalized_question = normalize_text(question)

    if not normalized_question:
        return None

    matches: list[tuple[_CatalogEntry, str, MatchType]] = []

    for entry in _load_catalog(str(Path(catalog_path))):
        aliases: tuple[tuple[str, MatchType], ...] = (
            (
                normalize_text(entry.searched_active_ingredient),
                "searched_active_ingredient",
            ),
            (
                normalize_text(entry.active_ingredients),
                "official_active_ingredient",
            ),
            (
                _commercial_name_alias(entry.name),
                "commercial_name",
            ),
        )

        for alias, match_type in aliases:
            if _contains_phrase(normalized_question, alias):
                matches.append((entry, alias, match_type))

    if not matches:
        return None

    registration_numbers = {
        entry.registration_number for entry, _, _ in matches
    }

    if len(registration_numbers) != 1:
        return None

    # Prefer the most specific alias when several aliases identify
    # the same medication.
    entry, alias, match_type = max(
        matches,
        key=lambda match: (
            len(match[1].split()),
            len(match[1]),
        ),
    )

    return MedicationMatch(
        registration_number=entry.registration_number,
        name=entry.name,
        active_ingredients=entry.active_ingredients,
        matched_alias=alias,
        match_type=match_type,
    )
