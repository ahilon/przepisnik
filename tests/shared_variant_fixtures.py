"""Synthetic matching audience portions shared by unit, HTTP and browser tests."""

from przepisnik.core.models import (
    Ingredient,
    Nutrition,
    Recipe,
    Source,
    UserMetadata,
    Variant,
    VariantKind,
)


def shared_variant_recipe() -> Recipe:
    """Build equal portions with different provenance and reversed ingredient order.

    Returns:
        Recipe: Fresh source objects with known amounts, ordered steps and personal metadata.
    """
    steps = ["Cook the rice.", "Serve warm."]
    female = Variant(
        ingredients=[
            Ingredient(name="Merge rice", amount=100, unit="g"),
            Ingredient(name="Merge water", amount=200, unit="ml"),
            Ingredient(name="Merge salt", raw="Salt to taste"),
        ],
        nutrition=Nutrition(kcal=400, protein_g=20, fat_g=10, carbs_g=50),
        source=Source(parser="agent", file="female-demo.txt", page=1),
    )
    male = female.model_copy(
        deep=True,
        update={
            "ingredients": list(reversed(female.ingredients)),
            "steps": steps.copy(),
            "source": Source(parser="agent", file="male-demo.txt", page=2),
        },
    )
    return Recipe(
        id="merge-example",
        title="Merge example",
        steps=steps,
        notes=["Keep the original source note."],
        user=UserMetadata(favorite=True, tags=["Original tag"], notes="Keep my note."),
        variants={VariantKind.FEMALE: female, VariantKind.MALE: male},
    )
