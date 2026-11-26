"""Check the nutrition editor with network responses supplied by Playwright."""

from http import HTTPStatus
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect
from ui_actions import ApplicationActions

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Nutrition, Recipe, VariantKind

_BUTTON = "Oszacuj wartości odżywcze z AI"
_TOTALS = Nutrition(kcal=615, protein_g=33, fat_g=20, carbs_g=70)


def test_estimate_button_is_disabled_without_key(app_page: Page, shared_recipe: Recipe) -> None:
    """Show how to enable estimating on the test instance without a key.

    Args:
        app_page: Browser connected to an isolated server with AI disabled.
        shared_recipe: Existing recipe to open in the editor.

    Returns:
        None: The estimate button is visible, disabled and describes the required setting.
    """
    app = ApplicationActions(app_page)
    app.search_product(shared_recipe.title)
    app.open_recipe(shared_recipe.title)
    app.open_editor()
    variant = app_page.locator('.editor-variant[data-kind="female"]')
    button = variant.get_by_role("button", name=_BUTTON)
    expect(button).to_be_visible()
    expect(button).to_be_disabled()
    expect(button).to_have_accessible_description("Aby włączyć, ustaw api_key na serwerze.")
    return None


@pytest.mark.parametrize("commit_estimate", [True, False], ids=["save", "cancel"])
def test_draft_estimate_uses_changed_amount_and_respects_save_or_cancel(
    page: Page, app_url: str, shared_recipe: Recipe, recipe_data: Path, commit_estimate: bool
) -> None:
    """Fill the correct draft fields and persist their provenance with the normal save.

    Args:
        page: Browser page with an isolated Playwright context.
        app_url: Actual local server or test container for database writes.
        shared_recipe: Stored pair with known ingredients and original nutrition.
        recipe_data: Disposable database used by this server.
        commit_estimate: Whether the user saves the changes or cancels editing.

    Returns:
        None: The draft uses current ingredients and persists only on save.
    """
    received: list[object] = []

    def enable_estimates(route: Route) -> None:
        """Advertise the capability on reads and forward all writes.

        Args:
            route: Browser request for the controlled recipe.

        Returns:
            None: Replies with the capability enabled for this browser only.
        """
        if route.request.method != "GET":
            route.continue_()
            return None
        response = route.fetch()
        route.fulfill(response=response, json={**response.json(), "nutrition_ai_available": True})
        return None

    def answer_estimate(route: Route) -> None:
        """Return fixed nourishment totals without leaving the browser context.

        Args:
            route: Browser POST containing current variant ingredients and servings.

        Returns:
            None: Saves the request for assertions and fulfills it locally.
        """
        received.append(route.request.post_data_json)
        route.fulfill(status=HTTPStatus.OK, json=_TOTALS.model_dump())
        return None

    page.context.route(f"**/api/recipes/{shared_recipe.id}", enable_estimates)
    page.context.route("**/api/nutrition/estimate", answer_estimate)
    page.goto(app_url)
    app = ApplicationActions(page)
    app.open_recipe(shared_recipe.title)
    app.open_editor()

    variant = page.locator('.editor-variant[data-kind="female"]')
    rice = variant.locator(".ingredient-row").first
    expect(rice.get_by_label("Nazwa składnika")).to_have_value("Merge rice")
    rice.get_by_label("Ilość", exact=True).fill("250")
    variant.get_by_label("Liczba porcji", exact=True).fill("2")
    variant.get_by_role("button", name=_BUTTON).click()

    for label, value in (
        ("Kalorie (kcal)", "615"),
        ("Białko (g)", "33"),
        ("Tłuszcz (g)", "20"),
        ("Węglowodany (g)", "70"),
    ):
        expect(variant.get_by_label(label)).to_have_value(value)
    expect(variant.get_by_text("Szacunek AI", exact=True)).to_be_visible()
    assert len(received) == 1
    assert isinstance(received[0], dict)
    assert received[0]["servings"] == 2
    assert received[0]["ingredients"][0]["name"] == "Merge rice"
    assert received[0]["ingredients"][0]["amount"] == 250
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(shared_recipe.id) == shared_recipe

    if not commit_estimate:
        page.get_by_role("button", name="Anuluj", exact=True).click()
        expect(page.locator("#editor")).to_be_hidden()
        with SqliteStore(recipe_data, read_only=True) as store:
            assert store.get(shared_recipe.id) == shared_recipe
        return None

    app.save_recipe()
    page.reload()
    app.open_recipe(shared_recipe.title)
    page.locator(".variant-tabs").get_by_role("button", name="Kobieta").click()
    expect(page.get_by_text("Szacunek AI", exact=True)).to_be_visible()
    with SqliteStore(recipe_data, read_only=True) as store:
        saved = store.get(shared_recipe.id)
    assert saved is not None
    assert saved.variants[VariantKind.FEMALE].nutrition == _TOTALS
    assert saved.variants[VariantKind.MALE] == shared_recipe.variants[VariantKind.MALE]
    return None
