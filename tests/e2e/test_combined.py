"""Exercise shared portions, safe fallback, shopping and print export in the browser."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from ui_actions import ApplicationActions

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Ingredient, Nutrition, Recipe, Variant, VariantKind


@pytest.fixture
def combined_recipe(recipe_data: Path) -> Recipe:
    """Store compatible portions with deliberately different source serving counts.

    Args:
        recipe_data: This test's disposable collection.

    Returns:
        Recipe: Stored original with a distinct family variant.
    """
    recipe = Recipe(
        id="combined-example",
        title="Combined example",
        steps=["Cook rice.", "Serve with egg."],
        variants={
            VariantKind.FEMALE: Variant(
                servings=2,
                ingredients=[
                    Ingredient(name="Rice", amount=120, unit="g", raw="Rice source: 120 g"),
                    Ingredient(
                        name="Egg", amount=2, unit="szt.", metric_amount=110, metric_unit="g"
                    ),
                    Ingredient(name="Salt", raw="Salt to taste"),
                ],
                nutrition=Nutrition(kcal=600, protein_g=20, fat_g=10, carbs_g=100),
            ),
            VariantKind.MALE: Variant(
                ingredients=[
                    Ingredient(name="Rice", amount=100, unit="g"),
                    Ingredient(
                        name="Egg", amount=2, unit="szt.", metric_amount=110, metric_unit="g"
                    ),
                    Ingredient(name="Salt", raw="Salt to taste"),
                ],
                nutrition=Nutrition(kcal=500, protein_g=30, fat_g=15, carbs_g=60),
            ),
            VariantKind.FAMILY: Variant(
                ingredients=[Ingredient(name="Family rice", amount=999, unit="g")]
            ),
        },
    )
    with SqliteStore(recipe_data) as store, store.transaction():
        return store.save(recipe)


def test_default_shared_view_scaling_and_original_editor(
    page: Page, app_url: str, combined_recipe: Recipe, recipe_data: Path
) -> None:
    """Default to a pair, scale from source quantities and keep editor inputs original.

    Args:
        page: Fresh browser page.
        app_url: Isolated application address.
        combined_recipe: Stored unmodified source variants.
        recipe_data: Disposable database path.

    Returns:
        None: Shared display, individual tabs, reopening and source integrity hold.
    """
    before = (recipe_data / "recipes.sqlite3").read_bytes()
    app = ApplicationActions(page)
    page.goto(app_url)
    app.open_recipe(combined_recipe.title)
    expect(page.locator("#variant")).to_have_value("combined")
    shared = page.locator(".variant-tabs").get_by_role("button", name="Dla dwojga", exact=True)
    expect(shared).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("2")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 160 g")
    expect(page.locator(".ingredients")).to_contain_text("Egg — 3 szt. — 165 g")
    expect(page.locator(".ingredients")).to_contain_text("Salt to taste")
    expect(page.locator(".nutrition strong").first).to_have_text("800")
    portions = page.locator("#detail-servings")
    app.set_servings("4")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 320 g")
    expect(page.locator(".nutrition strong").first).to_have_text("1600")
    page.locator(".variant-tabs").get_by_role("button", name="Kobieta", exact=True).click()
    expect(portions).to_have_value("2")
    expect(page.locator(".ingredients")).to_contain_text("Rice source: 120 g")
    shared.click()
    expect(portions).to_have_value("2")
    page.get_by_role("button", name="Edytuj przepis", exact=True).click()
    expect(page.locator(".editor-variant")).to_have_count(3)
    expect(page.locator("#female-servings")).to_have_value("2")
    expect(page.locator('[data-kind="female"] [data-field="amount"]').first).to_have_value("120")
    expect(page.locator("#male-servings")).to_have_value("1")
    expect(page.locator('[data-kind="combined"]')).to_have_count(0)
    page.get_by_role("button", name="Anuluj", exact=True).click()
    page.locator("#close-detail").click()
    page.get_by_role("button", name="Otwórz przepis: Combined example", exact=True).click()
    expect(shared).to_have_attribute("aria-pressed", "true")
    expect(portions).to_have_value("2")
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(combined_recipe.id) == combined_recipe
    assert (recipe_data / "recipes.sqlite3").read_bytes() == before


def test_shared_shopping_and_pdf_use_the_same_scaled_totals(
    page: Page, app_url: str, combined_recipe: Recipe, recipe_data: Path
) -> None:
    """Save the whole shared list once and export exactly the displayed shopping quantities.

    Args:
        page: Fresh browser page.
        app_url: Isolated application address.
        combined_recipe: Source recipe whose variants must remain unchanged.
        recipe_data: Disposable database path.

    Returns:
        None: Scaled ingredients persist and appear in the print/PDF sheet.
    """
    app = ApplicationActions(page)
    page.goto(app_url)
    app.open_recipe(combined_recipe.title)
    app.set_servings("4")
    app.add_recipe_to_shopping()
    expect(page.locator(".shopping-notice")).to_contain_text("4 porcji")
    saved = page.request.get(f"{app_url}/api/shopping-list").json()
    assert saved["revision"] == 1
    assert len(saved["items"]) == 3
    app.show_shopping_list()
    rice = page.locator(".shopping-row").filter(has=page.get_by_text("Rice", exact=True))
    egg = page.locator(".shopping-row").filter(has=page.get_by_text("Egg", exact=True))
    expect(rice.get_by_label("Ilość", exact=True)).to_have_value("320")
    expect(egg.get_by_label("Ilość", exact=True)).to_have_value("330")
    page.evaluate("() => { window.__printed = 0; window.print = () => window.__printed++; }")
    page.get_by_role("button", name="Eksportuj do PDF", exact=True).click()
    assert page.evaluate("window.__printed") == 1
    expect(page.locator("#shopping-print")).to_contain_text("Rice — 320 g")
    expect(page.locator("#shopping-print")).to_contain_text("Egg — 330 g")
    page.reload()
    page.get_by_role("button", name="Lista zakupów").click()
    expect(rice.get_by_label("Ilość", exact=True)).to_have_value("320")
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(combined_recipe.id) == combined_recipe


@pytest.mark.parametrize("difference", ["ingredients", "steps", "missing"])
def test_unavailable_shared_view_falls_back_with_a_short_notice(
    page: Page, app_url: str, combined_recipe: Recipe, recipe_data: Path, difference: str
) -> None:
    """Keep all recipes accessible and individual variants usable when sharing is unsafe.

    Args:
        page: Fresh browser page.
        app_url: Isolated application address.
        combined_recipe: Compatible source recipe to vary.
        recipe_data: Disposable database path.
        difference: Incompatibility or missing partner to introduce.

    Returns:
        None: Shared view is disabled with no ingredient or step details disclosed.
    """
    variants = dict(combined_recipe.variants)
    male = variants[VariantKind.MALE]
    if difference == "ingredients":
        variants[VariantKind.MALE] = male.model_copy(
            update={"ingredients": [Ingredient(name="Different product", amount=100, unit="g")]}
        )
    elif difference == "steps":
        variants[VariantKind.MALE] = male.model_copy(update={"steps": ["Different instruction."]})
    else:
        del variants[VariantKind.MALE]
    with SqliteStore(recipe_data) as store, store.transaction():
        store.save(combined_recipe.model_copy(update={"variants": variants}))
    app = ApplicationActions(page)
    page.goto(app_url)
    app.open_recipe(combined_recipe.title)
    expect(
        page.locator(".variant-tabs").get_by_role("button", name="Dla dwojga", exact=True)
    ).to_be_disabled()
    notice = page.locator(".variant-warning")
    expected = (
        "brak wariantu kobiety lub mężczyzny."
        if difference == "missing"
        else "różnice w składnikach lub krokach."
    )
    expect(notice).to_have_text(f"Dla dwojga niedostępne: {expected}")
    expect(page.locator(".ingredients")).to_contain_text("Rice source: 120 g")
    if difference != "missing":
        page.locator(".variant-tabs").get_by_role("button", name="Mężczyzna", exact=True).click()
        expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("1")


def test_explicit_variant_filter_overrides_shared_default(
    page: Page, app_url: str, combined_recipe: Recipe
) -> None:
    """Honor a linked individual variant and restore the shared default on reset.

    Args:
        page: Fresh browser page.
        app_url: Isolated application address.
        combined_recipe: Recipe used by both individual and shared views.

    Returns:
        None: Explicit filters, refresh and filter reset remain predictable.
    """
    page.goto(f"{app_url}/?variant=male")
    page.get_by_role("button", name=f"Otwórz przepis: {combined_recipe.title}", exact=True).click()
    tab = page.locator(".variant-tabs").get_by_role("button", name="Mężczyzna", exact=True)
    expect(tab).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".ingredients")).to_contain_text("Rice — 100 g")
    page.locator("#close-detail").click()
    page.reload()
    expect(page.locator("#variant")).to_have_value("male")
    page.locator("#reset").click()
    expect(page.locator("#variant")).to_have_value("combined")
    page.get_by_role("button", name="Otwórz przepis: Combined example", exact=True).click()
    expect(
        page.locator(".variant-tabs").get_by_role("button", name="Dla dwojga", exact=True)
    ).to_have_attribute("aria-pressed", "true")
