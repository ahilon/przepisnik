"""Verify hidden-only discovery and restoring recipes in browser collections."""

import re

from playwright.sync_api import Page, expect


def test_hide_and_restore_recipe_across_collections(app_page: Page) -> None:
    """Hide a favorite, preserve it across reload, and restore its original content."""
    page = app_page
    endpoint = f"{page.url.rstrip('/')}/api/recipes"
    created = page.request.post(
        endpoint,
        data={
            "recipe": {
                "title": "Visibility example",
                "steps": ["Cook."],
                "user": {"favorite": True, "tags": ["hidden-only-tag"]},
                "variants": {"family": {"servings": 1, "ingredients": [{"name": "Rice"}]}},
            }
        },
    )
    assert created.ok
    recipe_id = created.json()["id"]
    original = page.request.get(f"{endpoint}/{recipe_id}").json()
    page.reload()
    card = page.get_by_role("button", name="Otwórz przepis: Visibility example", exact=True)
    card.click()
    page.get_by_role("button", name="Ukryj przepis: Visibility example", exact=True).click()
    expect(
        page.get_by_role("button", name="Przywróć przepis: Visibility example", exact=True)
    ).to_be_visible()
    page.locator("#close-detail").click()
    expect(card).to_have_count(0)
    expect(page.locator("#count-hidden")).to_have_text("1")
    for query in ["", "?favorite=1", "?uncategorized=1", "?q=Visibility", "?tag=hidden-only-tag"]:
        result = page.request.get(f"{endpoint}{query}").json()
        assert recipe_id not in {recipe["id"] for recipe in result["items"]}
        assert "hidden-only-tag" not in result["tags"]
    page.locator('[data-collection="hidden"]').click()
    expect(page).to_have_url(re.compile(r"[?&]hidden=1(?:&|$)"))
    expect(card).to_be_visible()
    page.reload()
    expect(card).to_be_visible()
    expect(page.locator("#collection-title")).to_have_text("Ukryte przepisy")
    card.click()
    page.get_by_role("button", name="Przywróć przepis: Visibility example", exact=True).click()
    expect(
        page.get_by_role("button", name="Ukryj przepis: Visibility example", exact=True)
    ).to_be_visible()
    page.locator("#close-detail").click()
    expect(card).to_have_count(0)
    expect(page.locator("#count-hidden")).to_have_text("0")
    page.locator('[data-collection="all"]').click()
    expect(card).to_be_visible()
    page.locator('[data-collection="favorites"]').click()
    expect(page).to_have_url(re.compile(r"[?&]favorite=1(?:&|$)"))
    expect(card).to_be_visible()
    restored = page.request.get(f"{endpoint}/{recipe_id}").json()
    assert restored["user"]["hidden"] is False
    assert restored["user"]["favorite"] is True
    assert restored["steps"] == original["steps"]
    assert restored["variants"] == original["variants"]


def test_hidden_navigation_and_details_fit_mobile(app_page: Page) -> None:
    """Keep four collection tabs and recipe visibility actions usable on a phone."""
    page = app_page
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator('[data-collection="hidden"]')).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator(".card-button").first.click()
    page.get_by_role("button", name=re.compile(r"^Ukryj przepis:")).click()
    expect(page.get_by_role("button", name=re.compile(r"^Przywróć przepis:"))).to_be_visible()
    assert page.locator("#detail").evaluate("el => el.scrollWidth <= el.clientWidth")
    page.locator("#close-detail").click()
    page.locator('[data-collection="hidden"]').click()
    expect(page.locator(".recipe-card")).to_have_count(1)
