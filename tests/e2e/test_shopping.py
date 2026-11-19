"""Exercise the shared shopping list and cleaned-up application navigation."""

import re
from http import HTTPStatus
from importlib.metadata import version

from playwright.sync_api import Page, expect
from ui_actions import ApplicationActions


def test_custom_product_edit_check_reload_and_remove(app_page: Page) -> None:
    """Keep custom weights and checked products after reloading the application."""
    page = app_page
    app = ApplicationActions(page)
    app.open_shopping_list()
    app.add_product("Tomatoes", "500", "g")
    row = page.locator(".shopping-row").filter(has_text="Tomatoes")
    row.get_by_label("Ilość", exact=True).fill("750")
    row.get_by_role("button", name="Zapisz ilość: Tomatoes", exact=True).click()
    expect(page.locator("#shopping-status")).to_have_text("Lista zapisana.")
    page.get_by_role("checkbox", name="Mam: Tomatoes", exact=True).check()
    expect(page.get_by_role("region", name="Mam już")).to_contain_text("Tomatoes")
    expect(page.locator("#shopping-count")).to_have_text("0")
    page.reload()
    app.open_shopping_list()
    expect(page.get_by_role("checkbox", name="Mam: Tomatoes", exact=True)).to_be_checked()
    row = page.locator(".shopping-row").filter(has_text="Tomatoes")
    expect(row.get_by_label("Ilość", exact=True)).to_have_value("750")
    expect(row.get_by_label("Jednostka", exact=True)).to_have_value("g")
    row.get_by_role("button", name="Usuń produkt: Tomatoes", exact=True).click()
    expect(page.get_by_role("checkbox", name="Mam: Tomatoes", exact=True)).to_have_count(0)


def test_recipe_adds_scaled_ingredients_and_merges_compatible_units(app_page: Page) -> None:
    """Use the selected servings and convert kilograms when combining products."""
    page = app_page
    app = ApplicationActions(page)
    app.open_shopping_list()
    app.add_product("Shopping rice", "0.1", "kg")
    page.get_by_role("button", name="Zamknij listę zakupów", exact=True).click()
    response = page.request.post(
        f"{page.url.rstrip('/')}/api/recipes",
        data={
            "recipe": {
                "title": "Shopping recipe",
                "steps": ["Cook."],
                "variants": {
                    "family": {
                        "servings": 2,
                        "ingredients": [
                            {"name": "Shopping rice", "amount": 100, "unit": "g"},
                            {"name": "Shopping salt", "raw": "Salt to taste"},
                            {
                                "name": "Shopping egg",
                                "amount": 1,
                                "unit": "szt.",
                                "metric_amount": 55,
                                "metric_unit": "g",
                            },
                        ],
                    }
                },
            }
        },
    )
    assert response.ok
    recipe_id = response.json()["id"]
    original = page.request.get(f"{page.url.rstrip('/')}/api/recipes/{recipe_id}").json()
    page.reload()
    app.open_recipe("Shopping recipe")
    app.set_servings("4")
    app.add_recipe_to_shopping()
    expect(page.locator(".shopping-notice")).to_contain_text("Dodano składniki dla 4 porcji")
    expect(page.get_by_role("dialog", name="Shopping recipe")).to_be_visible()
    expect(page.get_by_role("dialog", name="Lista zakupów", exact=True)).to_be_hidden()
    expect(page.locator("#shopping-count")).to_have_text("3")
    app.show_shopping_list()
    expect(page.get_by_role("dialog", name="Lista zakupów", exact=True)).to_be_visible()
    rice = page.locator(".shopping-row").filter(has_text="Shopping rice")
    expect(rice.get_by_label("Ilość", exact=True)).to_have_value("300")
    expect(rice.get_by_label("Jednostka", exact=True)).to_have_value("g")
    salt = page.locator(".shopping-row").filter(has_text="Shopping salt")
    expect(salt.get_by_label("Ilość", exact=True)).to_have_value("")
    egg = page.locator(".shopping-row").filter(has_text="Shopping egg")
    expect(egg.get_by_label("Ilość", exact=True)).to_have_value("110")
    assert page.request.get(f"{page.url.rstrip('/')}/api/recipes/{recipe_id}").json() == original


def test_other_device_updates_are_not_overwritten(app_page: Page) -> None:
    """Show conflict feedback and load the newer list instead of losing its edits."""
    page = app_page
    app = ApplicationActions(page)
    app.open_shopping_list()
    endpoint = f"{page.url.rstrip('/')}/api/shopping-list"
    response = page.request.post(
        endpoint,
        data={"revision": 0, "items": [{"id": "remote", "name": "From another device"}]},
    )
    assert response.ok
    page.get_by_label("Produkt", exact=True).fill("Local product")
    page.get_by_role("button", name="Dodaj produkt", exact=True).click()
    expect(page.locator("#shopping-error")).to_contain_text("innym urządzeniu")
    expect(
        page.get_by_role("checkbox", name="Mam: From another device", exact=True)
    ).to_be_visible()
    assert page.request.get(endpoint).json()["items"][0]["name"] == "From another device"
    rejected = page.request.post(endpoint, data={"revision": 0, "items": []})
    assert rejected.status == HTTPStatus.CONFLICT
    forbidden = page.request.post(
        endpoint, data={"revision": 1, "items": []}, headers={"Origin": "https://example.invalid"}
    )
    assert forbidden.status == HTTPStatus.FORBIDDEN


def test_version_and_navigation_on_mobile(app_page: Page) -> None:
    """Expose the installed package version and usable shopping controls on a phone."""
    page = app_page
    app = ApplicationActions(page)
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator("#app-version")).to_contain_text(version("przepisnik"))
    expect(page.get_by_text("DOMOWA KSIĄŻKA KUCHARSKA", exact=True)).to_have_count(0)
    expect(page.locator(".sidebar-note")).to_have_count(0)
    app.open_shopping_list()
    app.add_product("Mobile product", "1", "szt.")
    assert page.locator("#shopping").evaluate("el => el.scrollWidth <= el.clientWidth")


def test_clear_list_requires_confirmation_and_persists(app_page: Page) -> None:
    """Clear both checked and unchecked products only after confirmation."""
    page = app_page
    app = ApplicationActions(page)
    app.open_shopping_list()
    clear = page.get_by_role("button", name="Wyczyść listę", exact=True)
    expect(clear).to_be_disabled()
    expect(page.get_by_role("button", name="Odśwież listę")).to_have_count(0)
    app.add_product("Keep", "1", "kg")
    assert clear.evaluate("el => getComputedStyle(el).color") == "rgb(179, 38, 30)"
    app.add_product("Have", "2", "szt.")
    page.get_by_role("checkbox", name="Mam: Have", exact=True).check()
    expect(page.get_by_role("region", name="Mam już")).to_contain_text("Have")
    page.once("dialog", lambda dialog: dialog.dismiss())
    clear.click()
    expect(page.locator(".shopping-row")).to_have_count(2)
    page.once("dialog", lambda dialog: dialog.accept())
    clear.click()
    expect(page.locator(".shopping-row")).to_have_count(0)
    expect(clear).to_be_disabled()
    expect(page.locator("#shopping-count")).to_have_text("0")
    page.reload()
    app.open_shopping_list()
    expect(page.locator(".shopping-row")).to_have_count(0)


def test_stale_clear_does_not_remove_another_devices_product(app_page: Page) -> None:
    """Reject clearing an old list after another client added a product."""
    page = app_page
    app = ApplicationActions(page)
    app.open_shopping_list()
    app.add_product("Local", "1", "g")
    endpoint = f"{page.url.rstrip('/')}/api/shopping-list"
    current = page.request.get(endpoint).json()
    current["items"].append({"id": "other", "name": "Other device"})
    assert page.request.post(endpoint, data=current).ok
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Wyczyść listę", exact=True).click()
    expect(page.locator("#shopping-error")).to_contain_text("innym urządzeniu")
    expect(page.locator(".shopping-row")).to_have_count(2)


def test_export_prints_only_products_to_buy(app_page: Page) -> None:
    """Render a print sheet with unchecked products and open the print dialog."""
    page = app_page
    app = ApplicationActions(page)
    app.open_shopping_list()
    export = page.get_by_role("button", name="Eksportuj do PDF", exact=True)
    expect(export).to_be_disabled()
    app.add_product("Print milk", "1.5", "l")
    app.add_product("Print owned", "1", "szt.")
    page.get_by_role("checkbox", name="Mam: Print owned", exact=True).check()
    expect(page.get_by_role("region", name="Mam już")).to_contain_text("Print owned")
    page.evaluate("() => { window.__printed = 0; window.print = () => window.__printed++; }")
    export.click()
    assert page.evaluate("window.__printed") == 1
    sheet = page.locator("#shopping-print")
    expect(sheet.locator("li")).to_have_count(1)
    expect(sheet).to_contain_text("Print milk — 1,5 l")
    page.emulate_media(media="print")
    expect(sheet).to_be_visible()
    expect(page.locator(".layout")).to_be_hidden()
    expect(page.locator("#shopping")).to_be_hidden()


def test_soup_tab_filters_by_dish_type(app_page: Page) -> None:
    """Use the soup shortcut tab as a dish filter separate from meal times."""
    page = app_page
    soups = page.get_by_role("button", name="Zupy", exact=True)
    soups.click()
    expect(soups).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#dish")).to_have_value("soup")
    expect(page).to_have_url(re.compile(r"dish=soup"))
    page.get_by_role("button", name="Obiady", exact=True).click()
    expect(soups).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#dish")).to_have_value("soup")
    page.get_by_role("button", name="Wszystko", exact=True).click()
    expect(page.locator("#dish")).to_have_value("")
    page.locator("#dish").select_option("soup")
    expect(soups).to_have_attribute("aria-pressed", "true")
