"""Verify recipe tag persistence, independent filtering and sidebar accessibility."""

import pytest
from playwright.sync_api import Page, expect
from ui_actions import ApplicationActions

RECIPE_TITLE = "Waniliowa owsianka z malinami, bananem i orzechami"
OTHER_RECIPE_TITLE = "Zupa kokosowa z tofu, limonką i makaronem ryżowym"
TAG_NAME = "E2E breakfast"


def test_added_tag_persists_after_reload(app_page: Page) -> None:
    """Keep a submitted recipe tag after the browser reloads saved data.

    Args:
        app_page: Browser showing this test's isolated demo collection.

    Returns:
        None: The same tag is visible before and after the page reload.
    """
    app = ApplicationActions(app_page)
    app.search_product("Owsianka")
    app.open_recipe(RECIPE_TITLE)
    app.add_tag(TAG_NAME)
    tag = app_page.locator("#detail").get_by_role(
        "button",
        name=f"Usuń tag: {TAG_NAME}",
        exact=True,
    )
    expect(tag).to_be_visible()

    app_page.reload()
    app.open_recipe(RECIPE_TITLE)
    expect(tag).to_be_visible()
    return None


def test_tag_filter_excludes_untagged_recipes(app_page: Page) -> None:
    """Filter by a saved tag independently of recipe search text.

    Args:
        app_page: Browser with fresh demo recipes, initially without user tags.

    Returns:
        None: Only the tagged recipe matches until the tag filter is cleared.
    """
    app = ApplicationActions(app_page)
    app.search_product("Owsianka")
    app.open_recipe(RECIPE_TITLE)
    app.add_tag(TAG_NAME)
    app_page.get_by_role("button", name="Zamknij szczegóły", exact=True).click()
    app.search_product("")

    recipe = app_page.get_by_role("button", name=f"Otwórz przepis: {RECIPE_TITLE}", exact=True)
    other_recipe = app_page.get_by_role(
        "button", name=f"Otwórz przepis: {OTHER_RECIPE_TITLE}", exact=True
    )
    expect(recipe).to_be_visible()
    expect(other_recipe).to_be_visible()
    tag_filter = app_page.get_by_label("Tag", exact=True)
    tag_filter.select_option(TAG_NAME)
    expect(app_page.locator(".recipe-card")).to_have_count(1)
    expect(recipe).to_be_visible()
    expect(other_recipe).to_have_count(0)

    app_page.reload()
    expect(tag_filter).to_have_value(TAG_NAME)
    expect(app_page.locator(".recipe-card")).to_have_count(1)
    expect(recipe).to_be_visible()
    expect(other_recipe).to_have_count(0)

    tag_filter.select_option("")
    expect(recipe).to_be_visible()
    expect(other_recipe).to_be_visible()
    return None


@pytest.mark.parametrize(
    ("width", "height"),
    [(1366, 600), (390, 844)],
    ids=["short-desktop", "mobile"],
)
def test_tag_filter_is_visible_without_scrolling(app_page: Page, width: int, height: int) -> None:
    """Keep the tag filter inside the viewport before any action can scroll to it.

    Args:
        app_page: Browser showing this test's isolated demo collection.
        width: Desktop or mobile viewport width in CSS pixels.
        height: Viewport height in CSS pixels.

    Returns:
        None: The complete tag filter is visible without clicking or scrolling.
    """
    app_page.set_viewport_size({"width": width, "height": height})
    expect(app_page.locator("#grid")).to_have_attribute("aria-busy", "false")
    tag_filter = app_page.get_by_label("Tag", exact=True)
    expect(tag_filter).to_be_visible()
    expect(tag_filter).to_be_in_viewport(ratio=1)
    return None
