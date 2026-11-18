"""Builders for small, valid domain objects and Respo-like sources used by unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pdf_fixtures import PdfFixtureWriter

from przepisnik.core.models import (
    Ingredient,
    Nutrition,
    Recipe,
    RecipeDraft,
    Variant,
    VariantData,
    VariantKind,
    recipe_id_for,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from przepisnik.core.database import SqliteStore

DEFAULT_TITLE = "Ryż z kurczakiem"
DEFAULT_STEPS = ("Ugotuj ryż.", "Podsmaż kurczaka.")
DEFAULT_INGREDIENTS = ("Ryż", "Kurczak")
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00"
    b"\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff"
    b"\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)

# A Respo recipe block in the current layout: wrapped title, ingredient name and
# quantity, an ingredient group, wrapped steps and the closing line.
RESPO_LINES = (
    "Posiłek 2 / 12:00-15:00",
    "Pinsa z sosem",
    "pomidorowym (liczba porcji: 2)",
    "591",
    "Kcal",
    "35 g",
    "B",
    "60 g",
    "W",
    "23 g",
    "T",
    "Pinsa – 0.5 sztuki (110 g)",
    "Oliwa z oliwek extra",
    "virgin – 1 łyżka (10 ml)",
    "Bazylia – 1 garść",
    "(5 g)",
    "Sos pomidorowy – 100 g",
    "Mozzarella – 2 plastry",
    "Do podania:",
    "Rukola – 20 g",
    "1. Piekarnik nagrzewamy",
    "do 220 stopni .",
    "2. Pieczemy 10 minut.",
    "Smacznego!",
)

# The older quantity-first layout; ``--`` marks a missing household measure.
LEGACY_RESPO_LINES = (
    "Posiłek 1 / 07:00-09:00",
    "Sałatka z pomidorami",
    "350",
    "Kcal",
    "12 g",
    "B",
    "50,5 g",
    "W",
    "8 g",
    "T",
    "2 sztuki pomidorów (320 g)",
    "0 -- makaronu spaghetti (60 g)",
    "1 łyżka oliwy",
    "z oliwek (10 ml)",
    "1.",
    "Wymieszaj składniki.",
    "Dzień 2",
)


def ingredients(*names: str) -> list[Ingredient]:
    """Return 100 g of each named ingredient."""
    return [Ingredient(name=name, metric_amount=100, metric_unit="g") for name in names]


def variant_data(
    names: Sequence[str] = DEFAULT_INGREDIENTS, *, kcal: float = 400, servings: int = 1
) -> VariantData:
    """Return portion data with nutrition and the named ingredients."""
    return VariantData(
        servings=servings,
        nutrition=Nutrition(kcal=kcal, protein_g=20, fat_g=10, carbs_g=50),
        ingredients=ingredients(*names),
    )


def draft(
    title: str = DEFAULT_TITLE,
    *,
    steps: Sequence[str] = DEFAULT_STEPS,
    names: Sequence[str] = DEFAULT_INGREDIENTS,
    kcal: float = 400,
) -> RecipeDraft:
    """Return a recipe draft as a parser would extract it."""
    return RecipeDraft(title=title, steps=list(steps), variant=variant_data(names, kcal=kcal))


def recipe(
    title: str = DEFAULT_TITLE,
    *,
    kinds: Sequence[VariantKind] = (VariantKind.FEMALE,),
    steps: Sequence[str] = DEFAULT_STEPS,
    names: Sequence[str] = DEFAULT_INGREDIENTS,
    kcal: float = 400,
    version: int = 1,
) -> Recipe:
    """Return a stored recipe with identical content in each requested variant."""
    data = dict(variant_data(names, kcal=kcal))
    return Recipe(
        id=recipe_id_for(title, version),
        title=title,
        version=version,
        steps=list(steps),
        variants={kind: Variant(**data) for kind in kinds},
    )


def persist(store: SqliteStore, item: Recipe) -> Recipe:
    """Save a recipe in its own committed transaction, as application operations do."""
    with store.transaction():
        return store.save(item)


def write_pdf(path: Path, pages: Sequence[Sequence[str]], *, image: bytes | None = None) -> Path:
    """Write a PDF with one text line per row and an optional image next to the first line."""
    return PdfFixtureWriter().write(path, pages, image)
