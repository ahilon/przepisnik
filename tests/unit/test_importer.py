"""Check transactional, idempotent imports into a real SQLite store."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from factories import PNG_BYTES, draft, persist, recipe

from przepisnik.core.database import SqliteStore
from przepisnik.core.importer import (
    ExtractedRecipe,
    ImportOptions,
    RecipeImporter,
    SourceRef,
)
from przepisnik.core.merge import MergeOutcome
from przepisnik.core.models import ImageData, MealType, Recipe, UserMetadata, VariantKind

FEMALE = VariantKind.FEMALE
MALE = VariantKind.MALE
ORIGIN = SourceRef(parser="respo", name="plan.pdf", sha256="abc")


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteStore]:
    """Return an empty writable store."""
    with SqliteStore(tmp_path) as opened:
        yield opened


def _stored(store: SqliteStore, recipe_id: str = "ryz-z-kurczakiem") -> Recipe:
    stored = store.get(recipe_id)
    assert stored is not None
    return stored


def _run(
    store: SqliteStore,
    items: list[ExtractedRecipe],
    kind: VariantKind = FEMALE,
    options: ImportOptions | None = None,
    origin: SourceRef = ORIGIN,
) -> dict[MergeOutcome, int]:
    report = RecipeImporter(store, store).run(items, kind, origin, options or ImportOptions())
    return report.counts


def test_source_key_prefers_hash_then_url_then_name() -> None:
    """Identify sources by content when possible."""
    assert ORIGIN.key == "abc"
    assert SourceRef(parser="agent", name="x", url="https://e.com").key == "https://e.com"
    assert SourceRef(parser="agent", name="notes.json").key == "notes.json"


def test_first_import_creates_recipes_and_registers_source(store: SqliteStore) -> None:
    """Create recipes with photos and provenance, then record the source."""
    items = [
        ExtractedRecipe(draft(), page=2, image=ImageData(PNG_BYTES, "png")),
        ExtractedRecipe(draft("Owsianka", names=["Płatki"])),
    ]
    assert _run(store, items) == {MergeOutcome.CREATED: 2}
    created = store.get("ryz-z-kurczakiem")
    assert created is not None
    assert created.image is not None
    source = created.variants[FEMALE].source
    assert source is not None
    assert (source.parser, source.file, source.sha256, source.page) == (
        "respo",
        "plan.pdf",
        "abc",
        2,
    )
    registered = store.find("abc")
    assert registered is not None
    assert registered.recipe_count == 2


def test_repeated_import_is_unchanged_even_after_edits(store: SqliteStore) -> None:
    """The ledger recognises consumed content after user edits and variant moves."""
    _run(store, [ExtractedRecipe(draft())])
    persist(store, _stored(store).model_copy(update={"title": "Mój ryż"}))
    assert _run(store, [ExtractedRecipe(draft())]) == {MergeOutcome.UNCHANGED: 1}
    assert len(store.all()) == 1


def test_duplicates_within_one_source_are_merged(store: SqliteStore) -> None:
    """Count repeated recipes of one plan once."""
    counts = _run(store, [ExtractedRecipe(draft()), ExtractedRecipe(draft())])
    assert counts == {MergeOutcome.CREATED: 1, MergeOutcome.UNCHANGED: 1}


def test_dry_run_writes_nothing(store: SqliteStore) -> None:
    """Report the outcome without saving recipes, ledger or source entries."""
    options = ImportOptions(dry_run=True)
    assert _run(store, [ExtractedRecipe(draft())], options=options) == {MergeOutcome.CREATED: 1}
    assert store.all() == []
    assert store.find("abc") is None
    assert store.imported("anything", FEMALE) is None


def test_other_variant_is_added_and_conflicts_are_reported(store: SqliteStore) -> None:
    """Add matching content as a variant and leave differing content for review."""
    _run(store, [ExtractedRecipe(draft())])
    male_plan = SourceRef(parser="respo", name="plan-m.pdf", sha256="def")
    items = [
        ExtractedRecipe(draft(kcal=700)),
        ExtractedRecipe(draft("Ryż z kurczakiem", names=["Kasza"]), page=5),
    ]
    report = RecipeImporter(store, store).run(items, MALE, male_plan, ImportOptions())
    assert report.counts == {MergeOutcome.VARIANT_ADDED: 1, MergeOutcome.CONFLICT: 1}
    [conflict] = report.conflicts
    assert (conflict.recipe_id, conflict.page) == ("ryz-z-kurczakiem", 5)
    assert conflict.candidate_ids == ["ryz-z-kurczakiem"]
    stored = store.get("ryz-z-kurczakiem")
    assert stored is not None
    assert set(stored.variants) == {FEMALE, MALE}


def test_force_replaces_already_imported_variant(store: SqliteStore) -> None:
    """Re-read consumed items and overwrite the variant, keeping user fields."""
    _run(store, [ExtractedRecipe(draft())])
    persist(store, _stored(store).model_copy(update={"user": UserMetadata(favorite=True)}))
    counts = _run(store, [ExtractedRecipe(draft(kcal=900))], options=ImportOptions(force=True))
    assert counts == {MergeOutcome.REPLACED: 1}
    stored = store.get("ryz-z-kurczakiem")
    assert stored is not None
    assert stored.user.favorite is True
    nutrition = stored.variants[FEMALE].nutrition
    assert nutrition is not None
    assert nutrition.kcal == 900


def test_enrich_meals_adds_source_categories(store: SqliteStore) -> None:
    """Add meal suggestions to existing recipes only when requested."""
    persist(store, recipe())
    lunch = draft().model_copy(update={"meal_types": [MealType.LUNCH]})
    plain = _run(store, [ExtractedRecipe(lunch)])
    assert plain == {MergeOutcome.UNCHANGED: 1}
    assert _stored(store).meal_types == []
    report = RecipeImporter(store, store).run(
        [ExtractedRecipe(lunch)], FEMALE, ORIGIN, ImportOptions(enrich_meals=True)
    )
    assert report.enriched_meals == ["ryz-z-kurczakiem"]
    assert _stored(store).meal_types == [MealType.LUNCH]


def test_duplicate_created_in_same_run_collects_all_meal_types(store: SqliteStore) -> None:
    """A recipe repeated in one plan gets the meal types of every occurrence."""
    breakfast = draft().model_copy(update={"meal_types": [MealType.BREAKFAST]})
    dinner = draft().model_copy(update={"meal_types": [MealType.DINNER]})
    _run(store, [ExtractedRecipe(breakfast), ExtractedRecipe(dinner)])
    stored = store.get("ryz-z-kurczakiem")
    assert stored is not None
    assert stored.meal_types == [MealType.BREAKFAST, MealType.DINNER]
