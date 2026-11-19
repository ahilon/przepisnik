"""Verify display-only serving scaling against isolated recipe data."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from ui_actions import ApplicationActions

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
    ApplicationActions(page).open_recipe(portion_recipe.title)
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("2")
    return page


def test_scale_servings_without_saving(
    portions_page: Page, portion_recipe: Recipe, recipe_data: Path
) -> None:
    """Recalculate from base values without changing data, steps or unknown amounts."""
    page = portions_page
    app = ApplicationActions(page)
    original_bytes = (recipe_data / "recipes.sqlite3").read_bytes()
    app.set_servings("4")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 200 g")
    expect(page.locator(".ingredients")).to_contain_text("Egg — 2 szt. — 110 g")
    expect(page.locator(".ingredients")).to_contain_text("Salt to taste")
    expect(page.locator(".ingredients")).to_contain_text("Optional sugar — 0 g")
    expect(page.locator(".nutrition strong").first).to_have_text("1200")
    expect(page.locator(".steps")).to_have_text("Cook for 10 minutes with 100 ml water.")
    app.set_servings("1")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 50 g")
    expect(page.locator(".ingredients")).to_contain_text("Egg — 0,5 szt. — 27,5 g")
    expect(page.locator(".nutrition strong").first).to_have_text("300")
    app.set_servings("2")
    expect(page.locator(".ingredients")).to_contain_text("Rice source: 100 g")
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(portion_recipe.id) == portion_recipe
    assert (recipe_data / "recipes.sqlite3").read_bytes() == original_bytes


@pytest.mark.parametrize("value", ["0", "-1", "20.1", ""])
def test_invalid_servings_keep_previous_quantities(portions_page: Page, value: str) -> None:
    """Reject empty, non-positive and excessive counts and allow correction."""
    page = portions_page
    app = ApplicationActions(page)
    app.set_servings(value)
    expect(page.locator("#portion-error")).to_be_visible()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_attribute("aria-invalid", "true")
    expect(page.locator(".ingredients")).to_contain_text("Rice source: 100 g")
    expect(page.locator(".nutrition strong").first).to_have_text("600")
    app.set_servings("3")
    expect(page.locator("#portion-error")).not_to_be_visible()
    expect(page.locator(".ingredients")).to_contain_text("Rice — 150 g")


def test_variant_and_reopen_reset_displayed_servings(portions_page: Page) -> None:
    """Reset to each variant's source portions without inventing nutrition data."""
    page = portions_page
    app = ApplicationActions(page)
    app.set_servings("4")
    page.locator(".variant-tabs").get_by_role("button", name="Kobieta", exact=True).click()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("1")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 25 g")
    expect(page.locator(".nutrition")).to_have_count(0)
    app.set_servings("2")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 50 g")
    page.locator(".variant-tabs").get_by_role("button", name="Rodzina", exact=True).click()
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("2")
    page.locator("#close-detail").click()
    app.open_recipe("Portion example")
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("2")


def test_editor_uses_original_values(portions_page: Page) -> None:
    """Keep scaled display values out of the recipe editor."""
    page = portions_page
    app = ApplicationActions(page)
    app.set_servings("4")
    page.get_by_role("button", name="Edytuj przepis", exact=True).click()
    expect(page.locator("#family-servings")).to_have_value("2")
    expect(page.locator('[data-kind="family"] [data-field="amount"]').first).to_have_value("100")


def test_fractional_servings_and_half_steps(portions_page: Page) -> None:
    """Accept arbitrary fractions while buttons advance by half a serving."""
    page = portions_page
    app = ApplicationActions(page)
    field = page.get_by_label("Liczba porcji", exact=True)
    increase = page.get_by_role("button", name="Zwiększ liczbę porcji o 0,5", exact=True)
    decrease = page.get_by_role("button", name="Zmniejsz liczbę porcji o 0,5", exact=True)
    increase.click()
    expect(field).to_have_value("2.5")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 125 g")
    app.set_servings("0.7")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 35 g")
    expect(page.locator(".nutrition strong").first).to_have_text("210")
    increase.click()
    expect(field).to_have_value("1.2")
    decrease.click()
    expect(field).to_have_value("0.7")
    decrease.click()
    expect(field).to_have_value("0.2")
    expect(decrease).to_be_disabled()
    app.set_servings("19.5")
    increase.click()
    expect(field).to_have_value("20")
    expect(increase).to_be_disabled()


def test_fractional_servings_are_used_in_shopping_list(portions_page: Page) -> None:
    """Send fractional quantities to shopping without changing the recipe."""
    page = portions_page
    app = ApplicationActions(page)
    app.set_servings("0.7")
    app.add_recipe_to_shopping()
    expect(page.locator(".shopping-notice")).to_contain_text("0,7 porcji")
    app.show_shopping_list()
    expect(page.get_by_role("dialog", name="Lista zakupów", exact=True)).to_be_visible()
    row = page.locator(".shopping-row").filter(has=page.get_by_text("Rice", exact=True))
    expect(row.get_by_label("Ilość", exact=True)).to_have_value("35")
