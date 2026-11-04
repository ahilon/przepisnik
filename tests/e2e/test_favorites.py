"""Verify favorite changes using an isolated recipe collection."""

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.sanity
def test_add_and_remove_favorite(app_page: Page) -> None:
    """Persist a favorite across reload and remove it from the favorites filter."""
    page = app_page
    expect(page.get_by_role("button", name="Otwórz przepis: Bajgiel z")).to_be_visible()
    page.get_by_role("button", name="Dodaj do ulubionych: Bajgiel").click()
    expect(page.get_by_role("button", name="Usuń z ulubionych: Bajgiel z")).to_have_attribute(
        "aria-pressed", "true"
    )
    page.get_by_role("button", name="♡ Ulubione").click()
    expect(page).to_have_url(re.compile(r"[?&]favorite=1(?:&|$)"))
    expect(page.get_by_role("button", name="Otwórz przepis: Bajgiel z")).to_be_visible()
    page.reload()
    expect(page.get_by_role("button", name="Otwórz przepis: Bajgiel z")).to_be_visible()
    page.get_by_role("button", name="Usuń z ulubionych: Bajgiel z").click()
    expect(page.get_by_role("button", name="Otwórz przepis: Bajgiel z")).not_to_be_visible()
