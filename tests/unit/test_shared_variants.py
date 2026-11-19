"""Check strict audience deduplication independently of persistence and UI."""

import pytest
from shared_variant_fixtures import shared_variant_recipe

from przepisnik.core.models import Ingredient, Nutrition, VariantKind
from przepisnik.core.shared_variants import SharedVariantMerger, VariantMergeConflictError


def test_merge_ignores_ingredient_order_and_keeps_unscaled_content() -> None:
    """Collapse equal portions while retaining every recipe-level field and input object.

    Returns:
        None: One shared portion contains 100 g of rice, not the summed pair.
    """
    recipe = shared_variant_recipe()
    before = recipe.model_dump()
    merger = SharedVariantMerger()
    assert merger.can_merge(recipe)
    merged = merger.merge(recipe)
    assert set(merged.variants) == {VariantKind.FAMILY}
    shared = merged.variants[VariantKind.FAMILY]
    assert shared.ingredients[0].amount == 100
    assert shared.servings == 1
    assert shared.nutrition == recipe.variants[VariantKind.FEMALE].nutrition
    assert shared.source == recipe.variants[VariantKind.FEMALE].source
    assert merged.steps_for(VariantKind.FAMILY) == recipe.steps
    assert merged.model_dump(exclude={"variants"}) == recipe.model_dump(exclude={"variants"})
    assert recipe.model_dump() == before
    shared.ingredients.reverse()
    assert recipe.model_dump() == before
    return None


@pytest.mark.parametrize(
    "difference",
    [
        "amount",
        "unit",
        "metric",
        "group",
        "raw",
        "duplicate",
        "name",
        "steps",
        "servings",
        "nutrition",
    ],
)
def test_content_differences_prevent_merge(difference: str) -> None:
    """Reject meaningful row, quantity, step, portion and nutrition differences.

    Args:
        difference: One independent change in the male portion.

    Returns:
        None: The eligibility check and merge both reject the altered recipe.
    """
    recipe = shared_variant_recipe()
    male = recipe.variants[VariantKind.MALE]
    ingredients = list(male.ingredients)
    changes: dict[str, object] = {}
    if difference == "steps":
        changes["steps"] = list(reversed(recipe.steps))
    elif difference == "servings":
        changes["servings"] = 2
    elif difference == "nutrition":
        changes["nutrition"] = Nutrition(kcal=401, protein_g=20, fat_g=10, carbs_g=50)
    elif difference == "duplicate":
        ingredients.append(ingredients[-1])
    else:
        fields: dict[str, dict[str, object]] = {
            "amount": {"amount": 101},
            "unit": {"unit": "kg"},
            "metric": {"metric_amount": 100, "metric_unit": "g"},
            "group": {"group": "To serve"},
            "raw": {"raw": "A different original instruction"},
            "name": {"name": "Different rice"},
        }
        ingredients[-1] = ingredients[-1].model_copy(update=fields[difference])
    changes["ingredients"] = ingredients
    variants = {**recipe.variants, VariantKind.MALE: male.model_copy(update=changes)}
    changed = recipe.model_copy(update={"variants": variants})
    before = changed.model_dump()
    merger = SharedVariantMerger()
    assert not merger.can_merge(changed)
    with pytest.raises(VariantMergeConflictError):
        merger.merge(changed)
    assert changed.model_dump() == before
    return None


@pytest.mark.parametrize("missing", [VariantKind.FEMALE, VariantKind.MALE])
def test_missing_partner_prevents_merge(missing: VariantKind) -> None:
    """Leave a single audience available without inventing its missing partner.

    Args:
        missing: Audience removed from the otherwise matching pair.

    Returns:
        None: No partial merge can be produced.
    """
    recipe = shared_variant_recipe()
    variants = {kind: variant for kind, variant in recipe.variants.items() if kind != missing}
    recipe = recipe.model_copy(update={"variants": variants})
    assert not SharedVariantMerger().can_merge(recipe)
    with pytest.raises(VariantMergeConflictError):
        SharedVariantMerger().merge(recipe)
    return None


@pytest.mark.parametrize("matching", [True, False])
def test_existing_shared_variant_is_preserved_or_blocks_merge(matching: bool) -> None:
    """Never overwrite an existing shared variant with different content.

    Args:
        matching: Whether the stored shared portion matches both audiences.

    Returns:
        None: Matching shared data is retained, while conflicting data prevents merging.
    """
    recipe = shared_variant_recipe()
    shared = recipe.variants[VariantKind.FEMALE].model_copy(deep=True)
    if not matching:
        shared = shared.model_copy(update={"ingredients": [Ingredient(name="Other dish")]})
    recipe = recipe.model_copy(update={"variants": {**recipe.variants, VariantKind.FAMILY: shared}})
    merger = SharedVariantMerger()
    assert merger.can_merge(recipe) is matching
    if matching:
        assert merger.merge(recipe).variants == {VariantKind.FAMILY: shared}
    else:
        with pytest.raises(VariantMergeConflictError):
            merger.merge(recipe)
    return None


@pytest.mark.parametrize("male_source", [True, False])
def test_available_source_is_used_when_female_has_no_provenance(male_source: bool) -> None:
    """Retain available provenance without making it a content comparison condition.

    Args:
        male_source: Whether either source record is available.

    Returns:
        None: Shared provenance uses the male reference or remains unknown.
    """
    recipe = shared_variant_recipe()
    female = recipe.variants[VariantKind.FEMALE].model_copy(update={"source": None})
    male = recipe.variants[VariantKind.MALE]
    if not male_source:
        male = male.model_copy(update={"source": None})
    recipe = recipe.model_copy(
        update={"variants": {VariantKind.FEMALE: female, VariantKind.MALE: male}}
    )
    merged = SharedVariantMerger().merge(recipe)
    assert merged.variants[VariantKind.FAMILY].source == male.source
    return None
