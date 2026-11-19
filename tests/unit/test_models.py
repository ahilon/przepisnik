"""Validate the recipe data model, its normalisation rules and helper functions."""

import pytest
from factories import recipe
from pydantic import ValidationError

from przepisnik.core.models import (
    DishType,
    Ingredient,
    MealType,
    Recipe,
    UserMetadata,
    Variant,
    VariantKind,
    recipe_id_for,
    slugify,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Zupa krem z dyni", "zupa-krem-z-dyni"),
        ("Łosoś w sosie koperkowym", "losos-w-sosie-koperkowym"),
        ("  Żółć!!  i   ćma ", "zolc-i-cma"),
        ("Pinsa (liczba porcji: 2)", "pinsa-liczba-porcji-2"),
        ("", ""),
    ],
)
def test_slugify_builds_ascii_hyphenated_keys(text: str, expected: str) -> None:
    """Remove Polish diacritics, punctuation and surrounding separators."""
    assert slugify(text) == expected


def test_recipe_id_includes_version_only_after_the_first() -> None:
    """Keep the plain slug for version 1 and suffix later versions."""
    assert recipe_id_for("Pinsa z sosem") == "pinsa-z-sosem"
    assert recipe_id_for("Pinsa z sosem", 3) == "pinsa-z-sosem-3"


def test_variant_kind_has_polish_labels() -> None:
    """Expose display labels for every audience."""
    assert [kind.label for kind in VariantKind] == ["Mężczyzna", "Kobieta", "Wspólne"]


def test_user_tags_are_stripped_and_deduplicated_case_insensitively() -> None:
    """Keep the first spelling of each tag."""
    metadata = UserMetadata(tags=["Obiad", " obiad ", "Szybkie", "OBIAD"])
    assert metadata.tags == ["Obiad", "Szybkie"]


def test_blank_user_tag_is_rejected() -> None:
    """Refuse tags that are empty after stripping whitespace."""
    with pytest.raises(ValidationError):
        UserMetadata(tags=["  "])


@pytest.mark.parametrize(
    "fields",
    [{"metric_amount": 10}, {"metric_unit": "g"}],
)
def test_metric_amount_and_unit_must_be_paired(fields: dict[str, object]) -> None:
    """Reject a metric amount without its unit and vice versa."""
    with pytest.raises(ValidationError, match="together"):
        Ingredient.model_validate({"name": "Mąka", **fields})


def test_ingredient_rejects_negative_and_non_finite_amounts() -> None:
    """Accept only finite, non-negative quantities."""
    for amount in (-1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            Ingredient(name="Mąka", amount=amount)


@pytest.mark.parametrize("image", ["", ".", "..", "../x.png", "a/b.png", "a\\b.png", "c:x.png"])
def test_recipe_image_must_be_a_plain_file_name(image: str) -> None:
    """Keep image references inside the recipe directory."""
    with pytest.raises(ValidationError, match="file name"):
        Recipe.model_validate({**recipe().model_dump(), "image": image})


def test_recipe_accepts_plain_image_name() -> None:
    """Allow content-addressed image names."""
    data = {**recipe().model_dump(), "image": "image-abc.png"}
    assert Recipe.model_validate(data).image == "image-abc.png"


def test_legacy_schema_version_is_upgraded_on_read() -> None:
    """Read v1 documents as the current schema without other changes."""
    data = {**recipe().model_dump(), "schema_version": 1}
    upgraded = Recipe.model_validate(data)
    assert upgraded.schema_version == 2
    assert upgraded.model_dump(exclude={"schema_version"}) == recipe().model_dump(
        exclude={"schema_version"}
    )


@pytest.mark.parametrize(
    "data",
    [
        {"unexpected": True},
        {"id": "Not A Slug"},
        {"steps": []},
        {"variants": {}},
        {"title": "   "},
    ],
)
def test_recipe_rejects_invalid_documents(data: dict[str, object]) -> None:
    """Refuse unknown fields, invalid IDs and missing required content."""
    with pytest.raises(ValidationError):
        Recipe.model_validate({**recipe().model_dump(), **data})


def test_effective_categories_prefer_user_overrides() -> None:
    """Use source categories until the user sets them, including an empty list."""
    source = recipe().model_copy(
        update={"meal_types": [MealType.LUNCH], "dish_types": [DishType.SOUP]}
    )
    assert source.effective_meal_types == [MealType.LUNCH]
    assert source.effective_dish_types == [DishType.SOUP]
    overridden = source.model_copy(
        update={"user": UserMetadata(meal_types=[], dish_types=[DishType.MAIN])}
    )
    assert overridden.effective_meal_types == []
    assert overridden.effective_dish_types == [DishType.MAIN]


def test_steps_for_uses_variant_steps_when_present() -> None:
    """Fall back to the shared steps for variants without their own and missing variants."""
    base = recipe(kinds=(VariantKind.FEMALE, VariantKind.MALE))
    male = Variant(**{**dict(base.variants[VariantKind.MALE]), "steps": ["Inny krok."]})
    updated = base.model_copy(update={"variants": {**base.variants, VariantKind.MALE: male}})
    assert updated.steps_for(VariantKind.MALE) == ["Inny krok."]
    assert updated.steps_for(VariantKind.FEMALE) == list(base.steps)
    assert updated.steps_for(VariantKind.FAMILY) == list(base.steps)


def test_models_are_immutable() -> None:
    """Prevent accidental in-place edits of validated data."""
    with pytest.raises(ValidationError):
        recipe().title = "Inny"  # type: ignore[misc]
