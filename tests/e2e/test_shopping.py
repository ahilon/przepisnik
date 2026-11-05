"""Exercise the shared shopping list and cleaned-up application navigation."""

from http import HTTPStatus
from importlib.metadata import version

from playwright.sync_api import Page, expect


def _open_list(page: Page) -> None:
    page.get_by_role("button", name="Lista zakupów").click()
    expect(page.locator("#shopping-status")).not_to_have_text("Wczytywanie listy…")


def _add_product(page: Page, name: str, amount: str, unit: str) -> None:
    page.get_by_label("Produkt", exact=True).fill(name)
    page.locator("#shopping-amount").fill(amount)
    page.locator("#shopping-unit").fill(unit)
    page.get_by_role("button", name="Dodaj produkt", exact=True).click()
    expect(page.get_by_role("checkbox", name=f"Mam: {name}", exact=True)).to_be_visible()


def test_custom_product_edit_check_reload_and_remove(app_page: Page) -> None:
    """Keep custom weights and checked products after reloading the application."""
    page = app_page
    _open_list(page)
    _add_product(page, "Tomatoes", "500", "g")
    row = page.locator(".shopping-row").filter(has_text="Tomatoes")
    row.get_by_label("Ilość", exact=True).fill("750")
    row.get_by_role("button", name="Zapisz ilość: Tomatoes", exact=True).click()
    expect(page.locator("#shopping-status")).to_have_text("Lista zapisana.")
    page.get_by_role("checkbox", name="Mam: Tomatoes", exact=True).check()
    expect(page.get_by_role("region", name="Mam już")).to_contain_text("Tomatoes")
    expect(page.locator("#shopping-count")).to_have_text("0")
    page.reload()
    _open_list(page)
    expect(page.get_by_role("checkbox", name="Mam: Tomatoes", exact=True)).to_be_checked()
    row = page.locator(".shopping-row").filter(has_text="Tomatoes")
    expect(row.get_by_label("Ilość", exact=True)).to_have_value("750")
    expect(row.get_by_label("Jednostka", exact=True)).to_have_value("g")
    row.get_by_role("button", name="Usuń produkt: Tomatoes", exact=True).click()
    expect(page.get_by_role("checkbox", name="Mam: Tomatoes", exact=True)).to_have_count(0)


def test_recipe_adds_scaled_ingredients_and_merges_compatible_units(app_page: Page) -> None:
    """Use the selected servings and convert kilograms when combining products."""
    page = app_page
    _open_list(page)
    _add_product(page, "Shopping rice", "0.1", "kg")
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
    page.get_by_role("button", name="Otwórz przepis: Shopping recipe", exact=True).click()
    page.get_by_label("Liczba porcji", exact=True).fill("4")
    page.get_by_label("Liczba porcji", exact=True).press("Tab")
    page.get_by_role("button", name="Dodaj do listy zakupów", exact=True).click()
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
    _open_list(page)
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
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator("#app-version")).to_contain_text(version("przepisnik"))
    expect(page.get_by_text("DOMOWA KSIĄŻKA KUCHARSKA", exact=True)).to_have_count(0)
    expect(page.locator(".sidebar-note")).to_have_count(0)
    _open_list(page)
    _add_product(page, "Mobile product", "1", "szt.")
    assert page.locator("#shopping").evaluate("el => el.scrollWidth <= el.clientWidth")
