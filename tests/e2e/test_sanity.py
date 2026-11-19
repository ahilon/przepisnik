"""Keep pull-request browser checks focused on seven core user journeys."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import ImageData, Ingredient, Recipe, Variant, VariantKind

pytestmark = pytest.mark.sanity
RECIPE_ID = "sanity-rice-bowl"
RECIPE_TITLE = "Sanity rice bowl"


@pytest.fixture
def sanity_recipe(recipe_data: Path) -> Recipe:
    """Store known portions and a real local image in disposable data.

    Args:
        recipe_data: Isolated collection created for this browser test.

    Returns:
        Recipe: Saved recipe whose amounts describe two servings.
    """
    recipe = Recipe(
        id=RECIPE_ID,
        title=RECIPE_TITLE,
        steps=["Cook the rice.", "Serve warm."],
        variants={
            VariantKind.FAMILY: Variant(
                servings=2,
                ingredients=[
                    Ingredient(name="Sanity rice", amount=100, unit="g"),
                    Ingredient(name="Sanity water", amount=200, unit="ml"),
                ],
            )
        },
    )
    image = ImageData((recipe_data / "empty_dish.png").read_bytes(), "png")
    with SqliteStore(recipe_data) as store, store.transaction():
        return store.save(recipe, image)


@pytest.fixture
def sanity_page(page: Page, app_url: str, sanity_recipe: Recipe) -> Page:
    """Open the browser after the controlled recipe has been saved.

    Args:
        page: Fresh Playwright page.
        app_url: Isolated server or explicitly selected container address.
        sanity_recipe: Known recipe added to this test's collection.

    Returns:
        Page: Loaded collection containing the controlled recipe.
    """
    page.goto(app_url)
    expect(
        page.get_by_role("button", name=f"Otwórz przepis: {sanity_recipe.title}", exact=True)
    ).to_be_visible()
    return page


def _open_recipe(page: Page) -> None:
    """Open the controlled recipe through its collection card.

    Args:
        page: Browser showing the recipe collection.

    Returns:
        None: The recipe detail dialog is open.
    """
    page.get_by_role("button", name=f"Otwórz przepis: {RECIPE_TITLE}", exact=True).click()
    expect(page.locator("#detail-title")).to_have_text(RECIPE_TITLE)
    return None


def _add_recipe_to_shopping(page: Page) -> None:
    """Add the recipe's original servings and open the shopping list.

    Args:
        page: Browser showing the controlled recipe's collection card.

    Returns:
        None: The shopping list contains the recipe ingredients.
    """
    _open_recipe(page)
    page.get_by_role("button", name="Dodaj do listy zakupów", exact=True).click()
    expect(page.locator(".shopping-notice")).to_contain_text("Dodano składniki")
    page.get_by_role("button", name="Pokaż listę", exact=True).click()
    expect(page.get_by_role("checkbox", name="Mam: Sanity rice", exact=True)).to_be_visible()
    return None


def test_recipe_list_loads_and_searches(sanity_page: Page) -> None:
    """Load the collection and locate a recipe using its title.

    Args:
        sanity_page: Browser with an isolated populated collection.

    Returns:
        None: Search leaves the matching recipe visible.
    """
    page = sanity_page
    expect(page.locator("#grid")).to_have_attribute("aria-busy", "false")
    page.get_by_role("searchbox").fill(RECIPE_TITLE)
    expect(page.locator(".recipe-card")).to_have_count(1)
    expect(page.get_by_role("heading", name=RECIPE_TITLE, exact=True)).to_be_visible()
    return None


def test_recipe_details_show_products_steps_and_photo(sanity_page: Page) -> None:
    """Read a recipe's quantities and preparation and load its stored image.

    Args:
        sanity_page: Browser containing the controlled recipe and photo.

    Returns:
        None: Actual recipe details and image are rendered.
    """
    page = sanity_page
    _open_recipe(page)
    expect(page.locator(".ingredients")).to_contain_text("Sanity rice — 100 g")
    expect(page.locator(".steps li")).to_have_text(["Cook the rice.", "Serve warm."])
    image = page.locator(".detail-hero")
    expect(image).to_be_visible()
    expect(image).to_have_js_property("complete", True)
    assert image.evaluate("image => image.naturalWidth > 0")
    expect(image).to_have_attribute("src", f"/images/{RECIPE_ID}")
    return None


def test_create_recipe_persists_after_reload(sanity_page: Page) -> None:
    """Create a recipe entirely through the form and find it after refresh.

    Args:
        sanity_page: Browser showing the recipe collection.

    Returns:
        None: Saved ingredients and instructions survive a page reload.
    """
    page = sanity_page
    title = "Sanity created recipe"
    page.get_by_role("button", name="+ Dodaj przepis", exact=True).click()
    page.locator("#edit-title").fill(title)
    page.locator('#editor [data-field="name"]').fill("Sanity oats")
    page.locator('#editor [data-field="amount"]').fill("50")
    page.locator('#editor [data-field="unit"]').fill("g")
    page.locator("#editor .step-editor textarea").fill("Mix the oats.")
    page.get_by_role("button", name="Zapisz przepis", exact=True).click()
    expect(page.locator("#editor")).to_be_hidden()
    page.reload()
    page.get_by_role("button", name=f"Otwórz przepis: {title}", exact=True).click()
    expect(page.locator(".ingredients")).to_contain_text("Sanity oats — 50 g")
    expect(page.locator(".steps")).to_have_text("Mix the oats.")
    return None


def test_edit_recipe_persists_after_reload(sanity_page: Page) -> None:
    """Edit an ingredient and preparation step and reload the saved recipe.

    Args:
        sanity_page: Browser containing the controlled source recipe.

    Returns:
        None: Updated quantities and instructions are read back from storage.
    """
    page = sanity_page
    _open_recipe(page)
    page.get_by_role("button", name="Edytuj przepis", exact=True).click()
    page.locator('#editor [data-field="amount"]').first.fill("150")
    page.locator("#editor .step-editor textarea").first.fill("Cook slowly.")
    page.get_by_role("button", name="Zapisz przepis", exact=True).click()
    expect(page.locator("#editor")).to_be_hidden()
    page.reload()
    _open_recipe(page)
    expect(page.locator(".ingredients")).to_contain_text("Sanity rice — 150 g")
    expect(page.locator(".steps li").first).to_have_text("Cook slowly.")
    return None


def test_serving_count_recalculates_products(sanity_page: Page) -> None:
    """Scale two servings to four while leaving the stored base quantities intact.

    Args:
        sanity_page: Browser containing a recipe for two servings.

    Returns:
        None: Both product quantities double and reopening restores their base.
    """
    page = sanity_page
    _open_recipe(page)
    portions = page.locator("#detail-servings")
    expect(portions).to_have_value("2")
    portions.fill("4")
    portions.press("Tab")
    expect(page.locator(".ingredients")).to_contain_text("Sanity rice — 200 g")
    expect(page.locator(".ingredients")).to_contain_text("Sanity water — 400 ml")
    page.reload()
    _open_recipe(page)
    expect(portions).to_have_value("2")
    expect(page.locator(".ingredients")).to_contain_text("Sanity rice — 100 g")
    return None


def test_recipe_products_persist_in_shopping_list(sanity_page: Page) -> None:
    """Add recipe products and read the saved shopping quantities after refresh.

    Args:
        sanity_page: Browser containing the controlled recipe.

    Returns:
        None: Rice and water retain their quantities on the shopping list.
    """
    page = sanity_page
    _add_recipe_to_shopping(page)
    page.reload()
    page.get_by_role("button", name="Lista zakupów").click()
    for name, amount, unit in [("Sanity rice", "100", "g"), ("Sanity water", "200", "ml")]:
        row = page.locator(".shopping-row").filter(has=page.get_by_text(name, exact=True))
        expect(row.get_by_label("Ilość", exact=True)).to_have_value(amount)
        expect(row.get_by_label("Jednostka", exact=True)).to_have_value(unit)
    return None


def test_shopping_checked_state_persists_after_reload(sanity_page: Page) -> None:
    """Remember which recipe product is already owned after reloading the page.

    Args:
        sanity_page: Browser containing the controlled recipe.

    Returns:
        None: Checked rice remains checked while water remains to buy.
    """
    page = sanity_page
    _add_recipe_to_shopping(page)
    page.get_by_role("checkbox", name="Mam: Sanity rice", exact=True).check()
    expect(page.get_by_role("region", name="Mam już")).to_contain_text("Sanity rice")
    page.reload()
    page.get_by_role("button", name="Lista zakupów").click()
    expect(page.get_by_role("checkbox", name="Mam: Sanity rice", exact=True)).to_be_checked()
    expect(page.get_by_role("checkbox", name="Mam: Sanity water", exact=True)).not_to_be_checked()
    return None
