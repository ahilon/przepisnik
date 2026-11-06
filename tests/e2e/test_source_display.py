"""Verify explicit source-provider and file provenance in recipe details."""

from pathlib import Path

from playwright.sync_api import Page, expect

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Source


def test_respo_provider_file_and_page_are_visible(
    page: Page, app_url: str, recipe_data: Path
) -> None:
    """Label Respo imports without losing the original PDF file reference."""
    with SqliteStore(recipe_data) as store, store.transaction():
        recipe = store.get("bajgiel-z-domowym-twarozkiem")
        assert recipe is not None
        variants = dict(recipe.variants)
        kind = next(iter(variants))
        variants[kind] = variants[kind].model_copy(
            update={
                "source": Source(
                    parser="respo",
                    file="example-respo.pdf",
                    sha256="a" * 64,
                    page=7,
                    meal_type_basis="respo_meal_number",
                )
            }
        )
        store.save(recipe.model_copy(update={"variants": variants}))
    page.goto(app_url)
    page.get_by_role("button", name=f"Otwórz przepis: {recipe.title}", exact=True).click()
    source = page.locator("#detail-content .source")
    expect(source).to_contain_text("Respo")
    expect(source).to_contain_text("example-respo.pdf")
    expect(source).to_contain_text("7")
