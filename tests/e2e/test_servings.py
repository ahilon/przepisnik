"""Verify display-only serving scaling against isolated recipe data."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Ingredient, Nutrition, Recipe, Variant, VariantKind


@pytest.fixture
def portion_recipe(recipe_data: Path) -> Recipe:
    """Add known quantities, raw source text and two different base portions."""
    recipe = Recipe(
        id="portion-example",
        title="Portion example",
        steps=["Cook for 10 minutes with 100 ml water."],
        variants={
            VariantKind.FAMILY: Variant(
                servings=2,
                ingredients=[
                    Ingredient(name="Rice", amount=100, unit="g", raw="Rice source: 100 g"),
                    Ingredient(
                        name="Egg", amount=1, unit="szt.", metric_amount=55, metric_unit="g"
                    ),
                    Ingredient(name="Salt", raw="Salt to taste"),
                    Ingredient(name="Optional sugar", amount=0, unit="g"),
                ],
                nutrition=Nutrition(kcal=600, protein_g=20, fat_g=10, carbs_g=100),
            ),
            VariantKind.FEMALE: Variant(
                servings=1,
                ingredients=[Ingredient(name="Rice", amount=25, unit="g")],
            ),
        },
    )
    with SqliteStore(recipe_data) as store, store.transaction():
        return store.save(recipe)


@pytest.fixture
def portions_page(page: Page, app_url: str, portion_recipe: Recipe) -> Page:
    """Open the controlled recipe after both server and test data are ready."""
    page.goto(app_url)
    page.get_by_role("button", name=f"Otwórz przepis: {portion_recipe.title}", exact=True).click()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("2")
    return page


def _set_servings(page: Page, value: str) -> None:
    field = page.get_by_label("Liczba porcji", exact=True)
    field.fill(value)
    field.press("Tab")


def test_scale_servings_without_saving(
    portions_page: Page, portion_recipe: Recipe, recipe_data: Path
) -> None:
    """Recalculate from base values without changing data, steps or unknown amounts."""
    page = portions_page
    original_bytes = (recipe_data / "recipes.sqlite3").read_bytes()
    _set_servings(page, "4")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 200 g")
    expect(page.locator(".ingredients")).to_contain_text("Egg — 2 szt. — 110 g")
    expect(page.locator(".ingredients")).to_contain_text("Salt to taste")
    expect(page.locator(".ingredients")).to_contain_text("Optional sugar — 0 g")
    expect(page.locator(".nutrition strong").first).to_have_text("1200")
    expect(page.locator(".steps")).to_have_text("Cook for 10 minutes with 100 ml water.")
    _set_servings(page, "1")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 50 g")
    expect(page.locator(".ingredients")).to_contain_text("Egg — 0,5 szt. — 27,5 g")
    expect(page.locator(".nutrition strong").first).to_have_text("300")
    _set_servings(page, "2")
    expect(page.locator(".ingredients")).to_contain_text("Rice source: 100 g")
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(portion_recipe.id) == portion_recipe
    assert (recipe_data / "recipes.sqlite3").read_bytes() == original_bytes


@pytest.mark.parametrize("value", ["0", "-1", "1.5", ""])
def test_invalid_servings_keep_previous_quantities(portions_page: Page, value: str) -> None:
    """Reject empty, fractional and non-positive counts and allow correction."""
    page = portions_page
    _set_servings(page, value)
    expect(page.locator("#portion-error")).to_be_visible()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_attribute("aria-invalid", "true")
    expect(page.locator(".ingredients")).to_contain_text("Rice source: 100 g")
    expect(page.locator(".nutrition strong").first).to_have_text("600")
    _set_servings(page, "3")
    expect(page.locator("#portion-error")).not_to_be_visible()
    expect(page.locator(".ingredients")).to_contain_text("Rice — 150 g")


def test_variant_and_reopen_reset_displayed_servings(portions_page: Page) -> None:
    """Reset to each variant's source portions without inventing nutrition data."""
    page = portions_page
    _set_servings(page, "4")
    page.locator(".variant-tabs").get_by_role("button", name="Kobieta", exact=True).click()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("1")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 25 g")
    expect(page.locator(".nutrition")).to_have_count(0)
    _set_servings(page, "2")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 50 g")
    page.locator(".variant-tabs").get_by_role("button", name="Rodzina", exact=True).click()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("2")
    page.locator("#close-detail").click()
    page.get_by_role("button", name="Otwórz przepis: Portion example", exact=True).click()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("2")


def test_editor_uses_original_values(portions_page: Page) -> None:
    """Keep scaled display values out of the recipe editor."""
    page = portions_page
    _set_servings(page, "4")
    page.get_by_role("button", name="Edytuj przepis", exact=True).click()
    expect(page.locator("#family-servings")).to_have_value("2")
    expect(page.locator('[data-kind="family"] [data-field="amount"]').first).to_have_value("100")
