"""Verify Respo classification, source identity and conservative duplicate handling."""

import inspect
from dataclasses import dataclass
from pathlib import Path

from przepisnik.core.database import SqliteStore
from przepisnik.core.importer import ExtractedRecipe, ImportOptions, RecipeImporter, SourceRef
from przepisnik.core.merge import MergeOutcome, merge_variant
from przepisnik.core.models import ImageData, Ingredient, MealType, VariantKind
from przepisnik.core.recipes import update_metadata
from przepisnik.parsers.base import RecipeParser
from przepisnik.parsers.document import ImageRef, TextLine
from przepisnik.parsers.respo import RespoParser


@dataclass(frozen=True)
class SampleDocument:
    """Minimal structured document independent of private diet-plan PDFs."""

    content: list[TextLine]

    def lines(self) -> list[TextLine]:
        """Return stable recipe text lines."""
        return self.content

    def images(self) -> list[ImageRef]:
        """Leave photo extraction out of these text/classification scenarios."""
        return []

    def extract_image(self, ref: ImageRef) -> ImageData:
        """Reject unexpected image requests."""
        raise ValueError(f"No test image with reference {ref.xref}")


def sample_recipes(quantity: int = 100) -> list[ExtractedRecipe]:
    """Extract all four configured meal slots with misleading time windows."""
    lines: list[TextLine] = []
    for number in range(1, 5):
        texts = [
            f"Posiłek {number} / 17:00-20:00",
            f"Test recipe {number}",
            "500",
            "Kcal",
            "10 g",
            "B",
            "50 g",
            "W",
            "20 g",
            "T",
            f"Rice \u2013 {quantity} g",
            "1. Cook rice.",
        ]
        lines.extend(TextLine(text, number, float(index)) for index, text in enumerate(texts))
    return RespoParser().parse_document(SampleDocument(lines)).recipes


def test_respo_inherits_shared_contract_and_classifies_all_meal_slots() -> None:
    """Apply the user-specified mapping instead of meal-time inference."""
    assert inspect.isabstract(RecipeParser)
    assert isinstance(RespoParser(), RecipeParser)
    recipes = sample_recipes()
    assert [recipe.draft.meal_types for recipe in recipes] == [
        [MealType.BREAKFAST, MealType.DINNER],
        [MealType.LUNCH],
        [MealType.BREAKFAST, MealType.DINNER],
        [MealType.SNACK],
    ]
    assert all(recipe.draft.meal_type_basis == "respo_meal_number" for recipe in recipes)


def test_reimports_skip_identical_content_and_add_only_missing_variants(recipe_data: Path) -> None:
    """Different PDF identities cannot duplicate already imported recipe content."""
    recipes = sample_recipes()
    first = SourceRef(parser="respo", name="first.pdf", sha256="a" * 64)
    second = SourceRef(parser="respo", name="second.pdf", sha256="b" * 64)
    with SqliteStore(recipe_data) as store:
        original_count = len(store.all())
        importer = RecipeImporter(store, store)
        created = importer.run(recipes, VariantKind.MALE, first, ImportOptions())
        recipe_id = "test-recipe-1"
        update_metadata(store, recipe_id, {"favorite": True, "hidden": True, "notes": "Keep this"})
        repeated = importer.run(recipes, VariantKind.MALE, second, ImportOptions())
        variant = importer.run(sample_recipes(200), VariantKind.FEMALE, second, ImportOptions())
        assert created.counts[MergeOutcome.CREATED] == len(recipes)
        assert repeated.counts == {MergeOutcome.UNCHANGED: len(recipes)}
        assert variant.counts == {MergeOutcome.VARIANT_ADDED: len(recipes)}
        assert len(store.all()) == original_count + len(recipes)
        saved = store.get(recipe_id)
        assert saved is not None
        assert saved.user.favorite and saved.user.hidden and saved.user.notes == "Keep this"
        source = saved.variants[VariantKind.MALE].source
        assert source is not None
        assert source.parser == "respo" and source.file == "first.pdf" and source.page == 1
        assert source.sha256 == first.sha256 and source.meal_type_basis == "respo_meal_number"


def test_overlap_creates_only_new_titles_and_preserves_conflicting_content(
    recipe_data: Path,
) -> None:
    """Report changed existing content rather than creating another recipe version."""
    recipes = sample_recipes()
    origin = SourceRef(parser="respo", name="sample.pdf")
    with SqliteStore(recipe_data) as store:
        importer = RecipeImporter(store, store)
        importer.run(recipes, VariantKind.MALE, origin, ImportOptions())
        snapshot = store.get("test-recipe-1")
        original_count = len(store.all())
        new = ExtractedRecipe(draft=recipes[0].draft.model_copy(update={"title": "New recipe"}))
        changed = ExtractedRecipe(
            draft=recipes[0].draft.model_copy(
                update={
                    "variant": recipes[0].draft.variant.model_copy(
                        update={
                            "ingredients": [
                                Ingredient(name="Rice", metric_amount=999, metric_unit="g")
                            ]
                        }
                    )
                }
            )
        )
        mixed = [recipes[0], new, changed]
        report = importer.run(mixed, VariantKind.MALE, origin, ImportOptions())
        assert report.counts == {
            MergeOutcome.UNCHANGED: 1,
            MergeOutcome.CREATED: 1,
            MergeOutcome.CONFLICT: 1,
        }
        assert len(store.all()) == original_count + 1
        assert store.get("test-recipe-1") == snapshot
        assert len(report.conflicts) == 1
        repeated = importer.run(mixed, VariantKind.MALE, origin, ImportOptions())
        assert repeated.counts == {MergeOutcome.UNCHANGED: 2, MergeOutcome.CONFLICT: 1}
        assert len(store.all()) == original_count + 1


def test_category_enrichment_preserves_manual_overrides(recipe_data: Path) -> None:
    """Enrich a repeated source while retaining personal meal selections."""
    recipe = sample_recipes()[0]
    old = ExtractedRecipe(
        draft=recipe.draft.model_copy(update={"meal_types": [MealType.BREAKFAST]})
    )
    origin = SourceRef(parser="respo", name="sample.pdf")
    with SqliteStore(recipe_data) as store:
        importer = RecipeImporter(store, store)
        importer.run([old], VariantKind.MALE, origin, ImportOptions())
        update_metadata(store, "test-recipe-1", {"meal_types": ["snack"]})
        report = importer.run([recipe], VariantKind.MALE, origin, ImportOptions(enrich_meals=True))
        saved = store.get("test-recipe-1")
        assert saved is not None
        assert saved.meal_types == [MealType.BREAKFAST, MealType.DINNER]
        assert saved.effective_meal_types == [MealType.SNACK]
        assert report.enriched_meals == [saved.id]


def test_explicit_missing_variant_preserves_different_steps_and_existing_content(
    recipe_data: Path,
) -> None:
    """Approved second variants retain their own instructions without replacing originals."""
    recipe = sample_recipes()[0]
    origin = SourceRef(parser="respo", name="female.pdf")
    with SqliteStore(recipe_data) as store:
        importer = RecipeImporter(store, store)
        importer.run([recipe], VariantKind.FEMALE, origin, ImportOptions())
        update_metadata(store, "test-recipe-1", {"favorite": True, "notes": "Personal note"})
        original = store.get("test-recipe-1")
        assert original is not None
        incoming = ExtractedRecipe(
            draft=recipe.draft.model_copy(
                update={
                    "steps": ["Prepare the male portion separately."],
                    "variant": sample_recipes(200)[0].draft.variant,
                }
            )
        )
        assert importer.run([incoming], VariantKind.MALE, origin, ImportOptions()).conflicts
        approved = ImportOptions(allow_variant_differences=True)
        report = importer.run([incoming], VariantKind.MALE, origin, approved)
        assert report.counts == {MergeOutcome.VARIANT_ADDED: 1}
        saved = store.get(original.id)
        assert saved is not None
        assert saved.variants[VariantKind.FEMALE] == original.variants[VariantKind.FEMALE]
        assert saved.steps_for(VariantKind.FEMALE) == original.steps
        assert saved.steps_for(VariantKind.MALE) == incoming.draft.steps
        assert saved.user == original.user
        assert importer.run([incoming], VariantKind.MALE, origin, approved).counts == {
            MergeOutcome.UNCHANGED: 1
        }
        replacement = ExtractedRecipe(
            draft=incoming.draft.model_copy(update={"steps": ["Changed again."]})
        )
        assert importer.run([replacement], VariantKind.MALE, origin, approved).conflicts
        assert store.get(original.id) == saved


def test_variant_approval_does_not_resolve_ambiguous_recipe_versions(recipe_data: Path) -> None:
    """A title shared by multiple recipes still requires choosing its target."""
    recipe = sample_recipes()[0]
    with SqliteStore(recipe_data) as store:
        importer = RecipeImporter(store, store)
        importer.run(
            [recipe],
            VariantKind.FEMALE,
            SourceRef(parser="respo", name="sample.pdf"),
            ImportOptions(),
        )
        first = store.get("test-recipe-1")
        assert first is not None
        second = first.model_copy(update={"id": "test-recipe-1-v2", "version": 2})
        different = recipe.draft.model_copy(update={"steps": ["Different preparation."]})
        result = merge_variant(
            [first, second], different, VariantKind.MALE, None, allow_variant_differences=True
        )
        assert result.outcome is MergeOutcome.CONFLICT
