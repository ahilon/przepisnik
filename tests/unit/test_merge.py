"""Cover conservative merging and explicitly forced variant replacement."""

from factories import draft, recipe

from przepisnik.core.merge import MergeOutcome, merge_variant, replace_variant
from przepisnik.core.models import MealType, Source, UserMetadata, VariantKind

FEMALE = VariantKind.FEMALE
MALE = VariantKind.MALE
SOURCE = Source(parser="respo", file="plan.pdf", page=2)


def test_new_title_creates_recipe_with_source() -> None:
    """Create a recipe with the incoming variant and deduplicated categories."""
    incoming = draft().model_copy(update={"meal_types": [MealType.LUNCH, MealType.LUNCH]})
    result = merge_variant([], incoming, FEMALE, SOURCE)
    assert result.outcome is MergeOutcome.CREATED
    assert result.recipe.id == "ryz-z-kurczakiem"
    assert result.recipe.meal_types == [MealType.LUNCH]
    assert list(result.recipe.variants) == [FEMALE]
    assert result.recipe.variants[FEMALE].source == SOURCE


def test_identical_variant_is_unchanged() -> None:
    """Skip content that is already stored for this variant."""
    stored = recipe()
    result = merge_variant([stored], draft(), FEMALE, SOURCE)
    assert result.outcome is MergeOutcome.UNCHANGED
    assert result.recipe is stored


def test_matching_ingredients_and_steps_add_missing_variant() -> None:
    """Add a different portion size as a new variant sharing the recipe steps."""
    stored = recipe()
    result = merge_variant([stored], draft(kcal=650), MALE, SOURCE)
    assert result.outcome is MergeOutcome.VARIANT_ADDED
    assert set(result.recipe.variants) == {FEMALE, MALE}
    assert result.recipe.variants[MALE].steps is None
    assert result.recipe.variants[FEMALE] == stored.variants[FEMALE]


def test_different_content_is_a_conflict() -> None:
    """Never merge recipes whose ingredients or steps differ without approval."""
    stored = recipe()
    for incoming in (draft(names=["Kasza", "Kurczak"]), draft(steps=["Inaczej."])):
        result = merge_variant([stored], incoming, MALE, SOURCE)
        assert result.outcome is MergeOutcome.CONFLICT
        assert result.recipe is stored
        assert result.reason


def test_existing_variant_with_other_content_is_a_conflict() -> None:
    """Do not overwrite a stored variant during a normal import."""
    result = merge_variant([recipe()], draft(kcal=650), FEMALE, SOURCE)
    assert result.outcome is MergeOutcome.CONFLICT


def test_approved_differences_add_variant_with_own_steps() -> None:
    """Explicit approval adds differing content to the only matching recipe."""
    stored = recipe()
    result = merge_variant(
        [stored], draft(steps=["Inaczej."]), MALE, SOURCE, allow_variant_differences=True
    )
    assert result.outcome is MergeOutcome.VARIANT_ADDED
    assert result.recipe.variants[MALE].steps == ["Inaczej."]
    assert result.recipe.steps == stored.steps


def test_approval_does_not_resolve_ambiguous_versions() -> None:
    """Several versions of a title stay a conflict even with approval."""
    versions = [recipe(names=["A"]), recipe(names=["B"], version=2)]
    result = merge_variant(versions, draft(), MALE, SOURCE, allow_variant_differences=True)
    assert result.outcome is MergeOutcome.CONFLICT


def test_forced_replacement_creates_or_skips_identical() -> None:
    """Behave like a merge for new titles and identical content."""
    assert replace_variant([], draft(), FEMALE, SOURCE).outcome is MergeOutcome.CREATED
    stored = recipe()
    assert replace_variant([stored], draft(), FEMALE, SOURCE).outcome is MergeOutcome.UNCHANGED


def test_forced_replacement_of_only_variant_replaces_shared_steps() -> None:
    """The only variant owns the recipe steps; user fields stay."""
    stored = recipe().model_copy(update={"user": UserMetadata(favorite=True, notes="Pyszne")})
    result = replace_variant([stored], draft(steps=["Nowy krok."], kcal=500), FEMALE, SOURCE)
    assert result.outcome is MergeOutcome.REPLACED
    assert result.recipe.steps == ["Nowy krok."]
    assert result.recipe.variants[FEMALE].steps is None
    nutrition = result.recipe.variants[FEMALE].nutrition
    assert nutrition is not None
    assert nutrition.kcal == 500
    assert result.recipe.user == stored.user


def test_forced_replacement_keeps_other_variants() -> None:
    """Replace one variant and keep shared steps for the others."""
    stored = recipe(kinds=(FEMALE, MALE))
    result = replace_variant([stored], draft(steps=["Nowy krok."]), MALE, SOURCE)
    assert result.outcome is MergeOutcome.REPLACED
    assert result.recipe.steps == stored.steps
    assert result.recipe.variants[FEMALE] == stored.variants[FEMALE]
    assert result.recipe.variants[MALE].steps == ["Nowy krok."]
    same_steps = replace_variant([stored], draft(kcal=900), MALE, SOURCE)
    assert same_steps.recipe.variants[MALE].steps is None


def test_forced_replacement_refuses_ambiguous_titles() -> None:
    """Never pick one of several versions sharing a title."""
    versions = [recipe(names=["A"]), recipe(names=["B"], version=2)]
    result = replace_variant(versions, draft(), FEMALE, SOURCE)
    assert result.outcome is MergeOutcome.CONFLICT
    assert result.reason
