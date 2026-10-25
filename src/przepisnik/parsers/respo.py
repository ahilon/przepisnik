"""Parser for diet-plan PDFs exported from the Respo app.

A recipe block looks like (``<dash>`` is an en dash)::

    Posiłek 2 / 12:00-15:00
    Pinsa z sosem pomidorowym (liczba porcji: 2)
    591 / Kcal / 35 g / B / 60 g / W / 23 g / T      (one value per line)
    Pinsa <dash> 0.5 sztuki (110 g)                  (ingredients, may wrap)
    Do podania:                                      (optional ingredient group)
    1. Piekarnik nagrzewamy ...                      (numbered steps, may wrap)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import ValidationError

from przepisnik.adapters.pdf import PdfDocument
from przepisnik.core.importer import ExtractedRecipe
from przepisnik.core.models import Ingredient, Nutrition, RecipeDraft, VariantData
from przepisnik.errors import SourceReadError
from przepisnik.parsers.base import ParseResult

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextlib import AbstractContextManager
    from pathlib import Path

    from przepisnik.parsers.document import Document, ImageRef, TextLine

    DocumentOpener = Callable[[Path], AbstractContextManager[Document]]

_NUMBER = r"\d+(?:[.,]\d+)?"
MEAL_HEADER = re.compile(r"^Posiłek \d+ / ")
DAY_HEADER = re.compile(r"^Dzień \d+$")
KCAL_VALUE = re.compile(rf"^{_NUMBER}$")
MACRO_VALUE = re.compile(rf"^({_NUMBER}) g$")
STEP_START = re.compile(r"^(\d+)\.(?:\s+(.*))?$")
DASH = "\u2013"  # en dash separating ingredient name and quantity
SEPARATOR = f" {DASH} "
GROUP_HEADER = re.compile(rf"^([^{DASH}]+):$")
BATCH_SUFFIX = re.compile(r"\s*\(liczba porcji:\s*(\d+)\)\s*$")
INGREDIENT = re.compile(rf"^(?P<name>.+?){SEPARATOR}(?P<quantity>.+)$")
QUANTITY_METRIC = re.compile(rf"^(?P<metric>{_NUMBER}) (?P<metric_unit>g|ml)$")
QUANTITY_FULL = re.compile(
    rf"^(?P<amount>{_NUMBER}) (?P<unit>.+?) \((?P<metric>{_NUMBER}) (?P<metric_unit>g|ml)\)$"
)
SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([.,;:!?])")

KCAL_LABEL = "Kcal"
MACRO_FIELDS = {"B": "protein_g", "W": "carbs_g", "T": "fat_g"}
PAGE_FOOTERS = frozenset({"Plan diety"})
RECIPE_END_LINES = frozenset({"Smacznego!"})
MAX_TITLE_LINES = 6
IMAGE_MAX_DISTANCE = 40.0
SINGLE_SERVING = 1
PDF_SUFFIX = ".pdf"


class RespoFormatError(ValueError):
    """A recipe block does not follow the Respo layout."""


class RespoParser:
    """Extract recipes, nutrition and dish photos from Respo diet-plan PDFs."""

    def __init__(self, opener: DocumentOpener = PdfDocument) -> None:
        """Create the parser.

        Args:
            opener: Opens a source path as a document context manager.
        """
        self._opener = opener

    @property
    def name(self) -> str:
        """Return the parser identifier."""
        return "respo"

    def can_parse(self, source: Path) -> bool:
        """Return True for PDFs containing Respo meal headers with calorie blocks."""
        if source.suffix.lower() != PDF_SUFFIX:
            return False
        try:
            with self._opener(source) as document:
                texts = [line.text for line in document.lines()]
        except SourceReadError:
            return False
        return KCAL_LABEL in texts and any(MEAL_HEADER.match(text) for text in texts)

    def parse(self, source: Path) -> ParseResult:
        """Extract all recipes from a Respo PDF file."""
        with self._opener(source) as document:
            return self.parse_document(document)

    def parse_document(self, document: Document) -> ParseResult:
        """Extract all recipes from an opened Respo document.

        Args:
            document: Opened source document.

        Returns:
            Parsed recipes and warnings about recipe blocks that were skipped.
        """
        lines = [line for line in document.lines() if line.text not in PAGE_FOOTERS]
        headers = [i for i, line in enumerate(lines) if MEAL_HEADER.match(line.text)]
        images = list(document.images())
        recipes: list[ExtractedRecipe] = []
        warnings: list[str] = []

        for position, start in enumerate(headers):
            end = headers[position + 1] if position + 1 < len(headers) else len(lines)
            header = lines[start]
            block = lines[start + 1 : end]
            if not _looks_like_recipe(block):
                continue  # plan overview pages reuse the meal header without a recipe
            try:
                draft = _parse_block(block)
            except (RespoFormatError, ValidationError) as exc:
                warnings.append(f"page {header.page}: skipped recipe block ({exc})")
                continue
            image_ref = _take_nearest_image(images, header)
            image = document.extract_image(image_ref) if image_ref else None
            if image is None:
                warnings.append(f"page {header.page}: no photo found for '{draft.title}'")
            recipes.append(ExtractedRecipe(draft=draft, page=header.page, image=image))
        return ParseResult(recipes=recipes, warnings=warnings)


def _looks_like_recipe(block: Sequence[TextLine]) -> bool:
    texts = [line.text for line in block[: MAX_TITLE_LINES + 2]]
    return KCAL_LABEL in texts


def _parse_block(block: Sequence[TextLine]) -> RecipeDraft:
    texts = [line.text for line in block]
    kcal_index = next((i for i, text in enumerate(texts) if KCAL_VALUE.match(text)), None)
    if kcal_index is None or kcal_index == 0 or kcal_index > MAX_TITLE_LINES:
        raise RespoFormatError("title or calories not found")
    if texts[kcal_index + 1 : kcal_index + 2] != [KCAL_LABEL]:
        raise RespoFormatError("calorie label not found")

    title, batch_portions = _split_title(" ".join(texts[:kcal_index]))
    nutrition, index = _parse_nutrition(texts, kcal_index)
    ingredients, index = _parse_ingredients(texts, index)
    steps = _parse_steps(texts[index:])
    return RecipeDraft(
        title=title,
        steps=steps,
        suggested_batch_portions=batch_portions,
        variant=VariantData(servings=SINGLE_SERVING, nutrition=nutrition, ingredients=ingredients),
    )


def _split_title(raw_title: str) -> tuple[str, int | None]:
    match = BATCH_SUFFIX.search(raw_title)
    if match is None:
        return _tidy(raw_title), None
    return _tidy(raw_title[: match.start()]), int(match.group(1))


def _parse_nutrition(texts: Sequence[str], kcal_index: int) -> tuple[Nutrition, int]:
    values: dict[str, float] = {"kcal": _to_float(texts[kcal_index])}
    index = kcal_index + 2
    for _ in MACRO_FIELDS:
        value, label = texts[index : index + 2] if index + 1 < len(texts) else ("", "")
        match = MACRO_VALUE.match(value)
        if match is None or label not in MACRO_FIELDS:
            raise RespoFormatError(f"unexpected macro line {value!r} {label!r}")
        values[MACRO_FIELDS[label]] = _to_float(match.group(1))
        index += 2
    return Nutrition.model_validate(values), index


def _parse_ingredients(texts: Sequence[str], start: int) -> tuple[list[Ingredient], int]:
    ingredients: list[Ingredient] = []
    buffer: str | None = None
    group: str | None = None
    index = start
    while index < len(texts) and not _is_step(texts[index], expected=1):
        text = texts[index]
        group_match = GROUP_HEADER.match(text)
        if group_match is not None:
            if buffer is not None:
                ingredients.append(_parse_ingredient(buffer, group))
            buffer, group = None, group_match.group(1).strip()
        elif buffer is None or _starts_new_ingredient(buffer, text):
            if buffer is not None:
                ingredients.append(_parse_ingredient(buffer, group))
            buffer = text
        else:
            buffer = f"{buffer} {text}"
        index += 1
    if buffer is not None:
        ingredients.append(_parse_ingredient(buffer, group))
    return ingredients, index


def _starts_new_ingredient(buffer: str, line: str) -> bool:
    """Decide whether ``line`` begins a new ingredient or continues a wrapped one."""
    if SEPARATOR not in buffer:
        return False  # the name itself wrapped before the dash
    return _is_complete_ingredient(buffer) or SEPARATOR in line


def _is_complete_ingredient(text: str) -> bool:
    match = INGREDIENT.match(text)
    if match is None:
        return False
    quantity = match.group("quantity")
    return bool(QUANTITY_FULL.match(quantity) or QUANTITY_METRIC.match(quantity))


def _parse_ingredient(text: str, group: str | None) -> Ingredient:
    raw = _tidy(text)
    match = INGREDIENT.match(raw)
    if match is None:
        return Ingredient(name=raw, group=group, raw=raw)
    name, quantity = match.group("name"), match.group("quantity")
    if full := QUANTITY_FULL.match(quantity):
        return Ingredient(
            name=name,
            amount=_to_float(full.group("amount")),
            unit=full.group("unit"),
            metric_amount=_to_float(full.group("metric")),
            metric_unit=full.group("metric_unit"),
            group=group,
            raw=raw,
        )
    if metric := QUANTITY_METRIC.match(quantity):
        return Ingredient(
            name=name,
            metric_amount=_to_float(metric.group("metric")),
            metric_unit=metric.group("metric_unit"),
            group=group,
            raw=raw,
        )
    return Ingredient(name=name, group=group, raw=raw)


def _parse_steps(texts: Sequence[str]) -> list[str]:
    steps: list[str] = []
    for text in texts:
        if text in RECIPE_END_LINES or DAY_HEADER.match(text):
            break
        match = STEP_START.match(text)
        if match is not None and int(match.group(1)) == len(steps) + 1:
            steps.append(match.group(2) or "")
        elif steps:
            steps[-1] = f"{steps[-1]} {text}"
    return [_tidy(step) for step in steps]


def _is_step(text: str, expected: int) -> bool:
    match = STEP_START.match(text)
    return match is not None and int(match.group(1)) == expected


def _take_nearest_image(images: list[ImageRef], header: TextLine) -> ImageRef | None:
    """Pop the image placed closest to the meal header on the same page."""
    candidates = [
        ref
        for ref in images
        if ref.page == header.page and abs(ref.top - header.top) <= IMAGE_MAX_DISTANCE
    ]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda ref: abs(ref.top - header.top))
    images.remove(nearest)
    return nearest


def _to_float(value: str) -> float:
    return float(value.replace(",", "."))


def _tidy(text: str) -> str:
    return SPACE_BEFORE_PUNCTUATION.sub(r"\1", " ".join(text.split()))
