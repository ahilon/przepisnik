"""Parse Respo diet-plan layouts from an in-memory document."""

from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from factories import LEGACY_RESPO_LINES, PNG_BYTES, RESPO_LINES

from przepisnik.core.models import ImageData, Ingredient, MealType
from przepisnik.errors import SourceReadError
from przepisnik.parsers.document import ImageRef, TextLine
from przepisnik.parsers.respo import RespoParser

HEADER_TOP = 100.0
LINE_HEIGHT = 15.0


@dataclass
class FakeDocument:
    """Document stub returning prepared lines and images."""

    text_lines: list[TextLine]
    image_refs: list[ImageRef] = field(default_factory=list)

    def lines(self) -> list[TextLine]:
        """Return the prepared lines."""
        return self.text_lines

    def images(self) -> list[ImageRef]:
        """Return the prepared image placements."""
        return self.image_refs

    def extract_image(self, ref: ImageRef) -> ImageData:
        """Return a PNG tagged with the image reference."""
        return ImageData(PNG_BYTES + bytes([ref.xref]), "png")


def _page(texts: Sequence[str], page: int = 1) -> list[TextLine]:
    return [TextLine(text, page, HEADER_TOP + LINE_HEIGHT * row) for row, text in enumerate(texts)]


def _image(xref: int, page: int = 1, top: float = HEADER_TOP) -> ImageRef:
    return ImageRef(xref=xref, page=page, top=top, width=100, height=100)


def _parse(document: FakeDocument) -> tuple[list[object], list[str]]:
    result = RespoParser().parse_document(document)
    return list(result.recipes), result.warnings


def test_current_layout_is_parsed_completely() -> None:
    """Read title, portions, macros, wrapped ingredients, groups, steps and photo."""
    document = FakeDocument(_page(RESPO_LINES), [_image(7, top=HEADER_TOP + 5)])
    result = RespoParser().parse_document(document)
    [item] = result.recipes
    recipe = item.draft
    assert recipe.title == "Pinsa z sosem pomidorowym"
    assert recipe.suggested_batch_portions == 2
    assert recipe.meal_types == [MealType.LUNCH]
    assert recipe.meal_type_basis == "respo_meal_number"
    assert recipe.meal_label == "Posiłek 2 / 12:00-15:00"
    assert recipe.variant.nutrition is not None
    assert recipe.variant.nutrition.model_dump() == {
        "kcal": 591,
        "protein_g": 35,
        "fat_g": 23,
        "carbs_g": 60,
    }
    expected = [
        ("Pinsa", 0.5, "sztuki", 110, "g", None),
        ("Oliwa z oliwek extra virgin", 1, "łyżka", 10, "ml", None),
        ("Bazylia", 1, "garść", 5, "g", None),
        ("Sos pomidorowy", None, None, 100, "g", None),
        ("Mozzarella", None, None, None, None, None),
        ("Rukola", None, None, 20, "g", "Do podania"),
    ]
    assert [_summary(ingredient) for ingredient in recipe.variant.ingredients] == expected
    assert recipe.variant.ingredients[4].raw == "Mozzarella – 2 plastry"
    assert recipe.steps == ["Piekarnik nagrzewamy do 220 stopni.", "Pieczemy 10 minut."]
    assert (item.page, item.image) == (1, ImageData(PNG_BYTES + b"\x07", "png"))
    assert result.warnings == []


def _summary(ingredient: Ingredient) -> tuple[object, ...]:
    return (
        ingredient.name,
        ingredient.amount,
        ingredient.unit,
        ingredient.metric_amount,
        ingredient.metric_unit,
        ingredient.group,
    )


def test_legacy_quantity_first_layout_is_parsed() -> None:
    """Read older exports, including missing household measures and comma decimals."""
    result = RespoParser().parse_document(FakeDocument(_page(LEGACY_RESPO_LINES)))
    [item] = result.recipes
    recipe = item.draft
    assert recipe.title == "Sałatka z pomidorami"
    assert recipe.meal_types == [MealType.BREAKFAST, MealType.DINNER]
    assert recipe.variant.nutrition is not None
    assert recipe.variant.nutrition.carbs_g == 50.5
    assert [_summary(ingredient) for ingredient in recipe.variant.ingredients] == [
        ("pomidorów", 2, "sztuki", 320, "g", None),
        ("makaronu spaghetti", None, None, 60, "g", None),
        ("oliwy z oliwek", 1, "łyżka", 10, "ml", None),
    ]
    assert recipe.steps == ["Wymieszaj składniki."]
    assert result.warnings == ["page 1: no photo found for 'Sałatka z pomidorami'"]


def test_unparseable_legacy_line_is_kept_verbatim() -> None:
    """Keep ingredient text that matches neither layout as the ingredient name."""
    lines = [*LEGACY_RESPO_LINES[:10], "Sól i pieprz", *LEGACY_RESPO_LINES[14:]]
    [item] = RespoParser().parse_document(FakeDocument(_page(lines))).recipes
    [ingredient] = item.draft.variant.ingredients
    assert (ingredient.name, ingredient.raw, ingredient.amount) == (
        "Sól i pieprz",
        "Sól i pieprz",
        None,
    )


def test_each_meal_gets_the_nearest_photo_on_its_page() -> None:
    """Assign images by distance on the same page and use each image once."""
    first = _page(RESPO_LINES, page=1)
    second = _page(LEGACY_RESPO_LINES, page=2)
    images = [_image(3, page=2), _image(9, page=1, top=HEADER_TOP + 60), _image(4, page=1)]
    result = RespoParser().parse_document(FakeDocument([*first, *second], images))
    assert [item.image.content[-1] for item in result.recipes if item.image] == [4, 3]


def test_page_footers_and_overview_headers_are_ignored() -> None:
    """Skip footer lines and plan overview headers without a recipe."""
    overview = _page(["Posiłek 1 / 07:00-09:00", "Owsianka", "Posiłek 2 / 12:00-15:00"])
    recipe_lines = _page(RESPO_LINES, page=2)
    footer = [TextLine("Plan diety", 2, recipe_lines[12].top)]
    lines = [*overview, *recipe_lines[:12], *footer, *recipe_lines[12:]]
    recipes, warnings = _parse(FakeDocument(lines))
    assert len(recipes) == 1
    assert warnings == ["page 2: no photo found for 'Pinsa z sosem pomidorowym'"]


@pytest.mark.parametrize(
    ("label", "meal_types", "warning"),
    [
        ("Posiłek 4 / 16:00-17:00", [MealType.SNACK], False),
        ("Posiłek 5 / 18:00-20:00", [MealType.DINNER], False),
        ("Posiłek 6 / 09:00-13:00", [], True),
    ],
)
def test_meal_number_mapping_falls_back_to_time_ranges(
    label: str, meal_types: list[MealType], warning: bool
) -> None:
    """Map known Respo meal numbers and warn when no meal type is known."""
    document = FakeDocument(_page([label, *RESPO_LINES[1:]]), [_image(1)])
    result = RespoParser().parse_document(document)
    assert result.recipes[0].draft.meal_types == meal_types
    assert any("meal type unknown" in text for text in result.warnings) is warning


@pytest.mark.parametrize(
    ("lines", "reason"),
    [
        (["Posiłek 2 / 12:00", "591", "Kcal", "1 g", "B"], "title or calories"),
        (["Posiłek 2 / 12:00", "Tytuł", "591", "kcal!", "Kcal"], "calorie label"),
        (["Posiłek 2 / 12:00", "Tytuł", "591", "Kcal", "1 g", "X"], "unexpected macro"),
        (["Posiłek 2 / 12:00", "Tytuł", "591", "Kcal", "1 g", "B", "2 g"], "unexpected macro"),
    ],
)
def test_malformed_blocks_are_skipped_with_warning(lines: list[str], reason: str) -> None:
    """Report blocks that do not follow the layout instead of failing the source."""
    recipes, warnings = _parse(FakeDocument(_page(lines)))
    assert recipes == []
    assert len(warnings) == 1
    assert "skipped recipe block" in warnings[0]
    assert reason in warnings[0]


def test_block_failing_validation_is_skipped_with_warning() -> None:
    """Skip recipes without steps reported by model validation."""
    lines = [line for line in RESPO_LINES if not line.startswith(("1. ", "2. "))]
    recipes, warnings = _parse(FakeDocument(_page(lines)))
    assert recipes == []
    assert "skipped recipe block" in warnings[0]


def test_can_parse_requires_pdf_with_respo_markers(tmp_path: Path) -> None:
    """Detect only PDF files containing meal headers and calorie labels."""
    recipe_doc = FakeDocument(_page(RESPO_LINES))
    parser = RespoParser(lambda _path: nullcontext(recipe_doc))
    assert parser.name == "respo"
    assert parser.can_parse(tmp_path / "plan.PDF") is True
    assert parser.can_parse(tmp_path / "plan.txt") is False
    other = RespoParser(lambda _path: nullcontext(FakeDocument(_page(["Inny dokument"]))))
    assert other.can_parse(tmp_path / "plan.pdf") is False


def test_can_parse_treats_unreadable_files_as_unsupported(tmp_path: Path) -> None:
    """Return False instead of failing for broken PDFs."""

    def broken(path: Path) -> nullcontext[FakeDocument]:
        raise SourceReadError(f"Cannot open {path}")

    assert RespoParser(broken).can_parse(tmp_path / "plan.pdf") is False


def test_parse_opens_source_with_opener(tmp_path: Path) -> None:
    """Parse a path through the injected document opener."""
    opened: list[Path] = []

    def opener(path: Path) -> nullcontext[FakeDocument]:
        opened.append(path)
        return nullcontext(FakeDocument(_page(RESPO_LINES)))

    result = RespoParser(opener).parse(tmp_path / "plan.pdf")
    assert opened == [tmp_path / "plan.pdf"]
    assert len(result.recipes) == 1
