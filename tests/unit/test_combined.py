"""Check shared portions against concrete quantities and incompatible recipes."""

from copy import deepcopy

import pytest

from przepisnik.core.combined import CombinedVariantBuilder
from przepisnik.core.models import Ingredient, Nutrition, Recipe, Variant, VariantKind


def _meal(female: Variant, male: Variant) -> Recipe:
    """Build a meal with explicit female and male source variants.

    Args:
        female: Ingredients and portions for the female source.
        male: Ingredients and portions for the male source.

    Returns:
        Recipe: An isolated recipe with shared preparation steps.
    """
    return Recipe(
        id="shared-rice",
        title="Shared rice",
        steps=["Cook rice.", "Serve."],
        variants={VariantKind.FEMALE: female, VariantKind.MALE: male},
    )


def test_one_serving_of_each_source_is_summed_without_mutation() -> None:
    """Normalize different source portion counts before adding ingredients and macros.

    Returns:
        None: The pair contains one serving from each untouched original.
    """
    original = _meal(
        Variant(
            servings=2,
            ingredients=[Ingredient(name="Rice", amount=120, unit="g", raw="Rice: 120 g")],
            nutrition=Nutrition(kcal=600, protein_g=20, fat_g=10, carbs_g=100),
        ),
        Variant(
            servings=4,
            ingredients=[Ingredient(name="Rice", amount=400, unit="g")],
            nutrition=Nutrition(kcal=2000, protein_g=80, fat_g=40, carbs_g=300),
        ),
    )
    before = deepcopy(original)
    combined = CombinedVariantBuilder().build(original)
    assert combined is not None
    assert combined.servings == 2
    assert combined.ingredients == [Ingredient(name="Rice", amount=160, unit="g")]
    assert combined.nutrition == Nutrition(kcal=800, protein_g=30, fat_g=15, carbs_g=125)
    assert combined.steps == ["Cook rice.", "Serve."]
    assert combined.source is None
    assert original == before


@pytest.mark.parametrize(
    ("female", "male", "amount", "unit"),
    [
        (
            Ingredient(name="Rice", amount=0.06, unit="kg"),
            Ingredient(name="Rice", amount=100, unit="g"),
            160,
            "g",
        ),
        (
            Ingredient(name="Milk", amount=0.2, unit="l"),
            Ingredient(name="Milk", amount=300, unit="ml"),
            500,
            "ml",
        ),
        (
            Ingredient(name="Egg", amount=1, unit="szt"),
            Ingredient(name="Egg", amount=2, unit="szt."),
            3,
            "szt.",
        ),
        (
            Ingredient(name="Rice", amount=0, unit="g"),
            Ingredient(name="Rice", amount=100, unit="g"),
            100,
            "g",
        ),
    ],
)
def test_compatible_units_and_zero_quantities(
    female: Ingredient, male: Ingredient, amount: float, unit: str
) -> None:
    """Sum known quantities using compatible physical or household units.

    Args:
        female: First source quantity.
        male: Second source quantity.
        amount: Expected combined amount.
        unit: Expected canonical unit.

    Returns:
        None: The expected quantity is present.
    """
    combined = CombinedVariantBuilder().build(
        _meal(Variant(ingredients=[female]), Variant(ingredients=[male]))
    )
    assert combined is not None
    assert combined.ingredients[0].amount == pytest.approx(amount)
    assert combined.ingredients[0].unit == unit


def test_product_order_whitespace_and_step_fallback_are_cosmetic() -> None:
    """Match products by name/group and resolve variant steps before comparison.

    Returns:
        None: Product order, casing and whitespace do not prevent safe combination.
    """
    original = _meal(
        Variant(
            ingredients=[
                Ingredient(name=" Rice ", amount=60, unit="g"),
                Ingredient(name="Salt", raw="Salt to taste"),
            ]
        ),
        Variant(
            ingredients=[
                Ingredient(name="salt", raw="salt   to taste"),
                Ingredient(name="RICE", amount=100, unit="g"),
            ],
            steps=["Cook  rice.", "SERVE."],
        ),
    )
    combined = CombinedVariantBuilder().build(original)
    assert combined is not None
    assert [item.name for item in combined.ingredients] == ["Rice", "Salt"]
    assert combined.ingredients[0].amount == 160
    assert combined.ingredients[1].amount is None
    assert combined.ingredients[1].raw == "Salt to taste"
    assert combined.nutrition is None


@pytest.mark.parametrize(
    ("female", "male"),
    [
        (
            [Ingredient(name="Rice", amount=60, unit="g")],
            [Ingredient(name="Pasta", amount=100, unit="g")],
        ),
        (
            [Ingredient(name="Rice", amount=60, unit="g")],
            [Ingredient(name="Rice", amount=100, unit="g"), Ingredient(name="Salt")],
        ),
        (
            [Ingredient(name="Rice", amount=60, unit="g")],
            [Ingredient(name="Rice", amount=100, unit="ml")],
        ),
        ([Ingredient(name="Rice", amount=60, unit="g")], [Ingredient(name="Rice")]),
        ([Ingredient(name="Rice", amount=0, unit="g")], [Ingredient(name="Rice")]),
        ([Ingredient(name="Salt", raw="To taste")], [Ingredient(name="Salt", raw="One pinch")]),
        (
            [Ingredient(name="Rice", amount=60, unit="g", group="Sauce")],
            [Ingredient(name="Rice", amount=100, unit="g")],
        ),
        (
            [Ingredient(name="Rice", amount=60, unit="g")],
            [
                Ingredient(name="Rice", amount=100, unit="g"),
                Ingredient(name="Rice", amount=20, unit="g"),
            ],
        ),
        (
            [Ingredient(name="Rice", amount=1e308, unit="g")],
            [Ingredient(name="Rice", amount=1e308, unit="g")],
        ),
        ([Ingredient(name="Salt", unit="pinch")], [Ingredient(name="Salt", unit="spoon")]),
    ],
)
def test_incompatible_or_ambiguous_ingredients_disable_the_whole_shared_view(
    female: list[Ingredient], male: list[Ingredient]
) -> None:
    """Reject complete combinations rather than returning a partial ingredient list.

    Args:
        female: First source product list.
        male: Incompatible or ambiguous second list.

    Returns:
        None: No shared variant is produced and originals remain intact.
    """
    original = _meal(Variant(ingredients=female), Variant(ingredients=male))
    before = deepcopy(original)
    assert CombinedVariantBuilder().build(original) is None
    assert original == before


@pytest.mark.parametrize("steps", [["Cook different rice.", "Serve."], ["Serve.", "Cook rice."]])
def test_different_steps_or_step_order_disable_combination(steps: list[str]) -> None:
    """Reject changed instructions even when the ingredient lists match.

    Args:
        steps: Male preparation differing in text or order.

    Returns:
        None: The shared view is unavailable.
    """
    original = _meal(
        Variant(ingredients=[Ingredient(name="Rice", amount=60, unit="g")]),
        Variant(ingredients=[Ingredient(name="Rice", amount=100, unit="g")], steps=steps),
    )
    assert CombinedVariantBuilder().build(original) is None


@pytest.mark.parametrize("kind", [VariantKind.FEMALE, VariantKind.MALE, VariantKind.FAMILY])
def test_a_single_variant_never_substitutes_for_a_pair(kind: VariantKind) -> None:
    """Require both actual source variants, keeping family independent.

    Args:
        kind: The only available source variant.

    Returns:
        None: A missing partner disables the shared view.
    """
    original = Recipe(
        id="single",
        title="Single",
        steps=["Cook."],
        variants={kind: Variant(ingredients=[Ingredient(name="Rice")])},
    )
    assert CombinedVariantBuilder().build(original) is None


def test_metric_quantities_can_replace_different_household_units() -> None:
    """Use complete gram totals without adding incompatible spoons to pieces.

    Returns:
        None: Only the common metric representation is retained.
    """
    original = _meal(
        Variant(
            ingredients=[
                Ingredient(name="Cheese", amount=1, unit="slice", metric_amount=30, metric_unit="g")
            ]
        ),
        Variant(
            ingredients=[
                Ingredient(name="Cheese", amount=2, unit="spoon", metric_amount=50, metric_unit="g")
            ]
        ),
    )
    combined = CombinedVariantBuilder().build(original)
    assert combined is not None
    assert combined.ingredients == [Ingredient(name="Cheese", metric_amount=80, metric_unit="g")]


def test_metric_and_household_weight_representations_can_be_combined() -> None:
    """Recognize a complete weight even when only one source has a metric field.

    Returns:
        None: Both quantities contribute to the gram total.
    """
    original = _meal(
        Variant(ingredients=[Ingredient(name="Rice", metric_amount=60, metric_unit="g")]),
        Variant(ingredients=[Ingredient(name="Rice", amount=0.1, unit="kg")]),
    )
    combined = CombinedVariantBuilder().build(original)
    assert combined is not None
    assert combined.ingredients[0].metric_amount == 160
    assert combined.ingredients[0].metric_unit == "g"


def test_incompatible_metric_dimensions_are_not_hidden_by_household_units() -> None:
    """Reject grams versus millilitres even when both rows also say one spoon.

    Returns:
        None: Conflicting physical dimensions make combination unavailable.
    """
    original = _meal(
        Variant(
            ingredients=[
                Ingredient(name="Sauce", amount=1, unit="spoon", metric_amount=60, metric_unit="g")
            ]
        ),
        Variant(
            ingredients=[
                Ingredient(
                    name="Sauce", amount=1, unit="spoon", metric_amount=100, metric_unit="ml"
                )
            ]
        ),
    )
    assert CombinedVariantBuilder().build(original) is None


@pytest.mark.parametrize("missing", [VariantKind.FEMALE, VariantKind.MALE])
def test_missing_nutrition_never_produces_a_partial_total(missing: VariantKind) -> None:
    """Keep combined ingredients usable without displaying incomplete macro totals.

    Args:
        missing: Source variant whose nutrition is unknown.

    Returns:
        None: Shared nutrition is unknown when either partner lacks values.
    """
    nutrition = Nutrition(kcal=500, protein_g=20, fat_g=10, carbs_g=50)
    original = _meal(
        Variant(
            ingredients=[Ingredient(name="Rice", amount=60, unit="g")],
            nutrition=None if missing == VariantKind.FEMALE else nutrition,
        ),
        Variant(
            ingredients=[Ingredient(name="Rice", amount=100, unit="g")],
            nutrition=None if missing == VariantKind.MALE else nutrition,
        ),
    )
    combined = CombinedVariantBuilder().build(original)
    assert combined is not None
    assert combined.ingredients[0].amount == 160
    assert combined.nutrition is None
