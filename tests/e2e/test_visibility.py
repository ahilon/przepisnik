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


def test_editor_actions_stay_visible_while_scrolling(app_page: Page) -> None:
    """Keep save and cancel reachable at every scroll position of a long editor."""
    page = app_page
    page.set_viewport_size({"width": 1280, "height": 700})
    page.get_by_role("button", name="+ Dodaj przepis", exact=True).click()
    editor = page.locator("#editor")
    save = page.get_by_role("button", name="Zapisz przepis", exact=True)
    cancel = page.get_by_role("button", name="Anuluj", exact=True)
    assert editor.evaluate("el => el.scrollHeight > el.clientHeight + 200")
    for position in ("0", "el.scrollHeight / 2", "el.scrollHeight"):
        editor.evaluate(f"el => {{ el.scrollTop = {position}; }}")
        expect(save).to_be_in_viewport()
        expect(cancel).to_be_in_viewport()
        box = editor.bounding_box()
        footer = page.locator(".editor-footer").bounding_box()
        assert box and footer and footer["y"] + footer["height"] <= box["y"] + box["height"] + 1
    cancel.click()
    expect(editor).to_be_hidden()


def test_custom_tags_from_detail_and_editor(app_page: Page) -> None:
    """Add and remove own tags in the recipe view and in the editor."""
    page = app_page
    endpoint = f"{page.url.rstrip('/')}/api/recipes"
    created = page.request.post(
        endpoint,
        data={
            "recipe": {
                "title": "Tag example",
                "steps": ["Cook."],
                "variants": {"family": {"servings": 1, "ingredients": [{"name": "Rice"}]}},
            }
        },
    )
    assert created.ok
    recipe_id = created.json()["id"]
    page.reload()
    page.get_by_role("button", name="Otwórz przepis: Tag example", exact=True).click()
    field = page.locator("#detail-tags")
    field.fill("#Na imprezę, szybkie")
    field.press("Enter")
    chips = page.locator("#detail .tag-chip")
    expect(chips).to_contain_text(["#Na imprezę", "#szybkie"])
    expect(page.locator("#tag option[value='szybkie']")).to_have_count(1)
    assert page.request.get(f"{endpoint}/{recipe_id}").json()["user"]["tags"] == [
        "Na imprezę",
        "szybkie",
    ]
    field.fill("SZYBKIE")
    page.get_by_role("button", name="Dodaj tag", exact=True).click()
    expect(chips).to_have_count(2)
    page.get_by_role("button", name="Usuń tag: Na imprezę", exact=True).click()
    expect(chips).to_have_count(1)
    page.get_by_role("button", name="Edytuj przepis", exact=True).click()
    editor_field = page.locator("#edit-tags")
    expect(page.locator("#editor .tag-chip")).to_contain_text(["#szybkie"])
    editor_field.fill("obiad w 15 min")
    editor_field.press("Enter")
    expect(page.locator("#editor")).to_be_visible()
    editor_field.fill("wege")
    page.get_by_role("button", name="Zapisz przepis", exact=True).click()
    expect(page.locator("#editor")).to_be_hidden()
    assert page.request.get(f"{endpoint}/{recipe_id}").json()["user"]["tags"] == [
        "szybkie",
        "obiad w 15 min",
        "wege",
    ]
    expect(page.locator("#detail .tag-chip")).to_have_count(3)
