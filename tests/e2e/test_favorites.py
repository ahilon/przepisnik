"""Browser tests for recipe favorites."""

from playwright.sync_api import Page, expect


def test_add_and_remove_favorite(app_page: Page) -> None:
    """Add a favorite, find it in the favorites filter and remove it."""
    page = app_page
    expect(page.get_by_role("button", name="Otwórz przepis: Bajgiel z")).to_be_visible()
    page.get_by_role("button", name="Dodaj do ulubionych: Bajgiel").click()
    page.get_by_role("button", name="♡ Ulubione").click()
    expect(page.get_by_role("button", name="Otwórz przepis: Bajgiel z")).to_be_visible()
    page.get_by_role("button", name="Usuń z ulubionych: Bajgiel z").click()
    expect(page.get_by_role("button", name="Otwórz przepis: Bajgiel z")).not_to_be_visible()
