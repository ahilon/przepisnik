"""Exercise approved recipe variants with visibly different preparation steps."""

from pathlib import Path

from playwright.sync_api import Page, expect

from przepisnik.core.database import SqliteStore
from przepisnik.core.importer import ExtractedRecipe, ImportOptions, RecipeImporter, SourceRef
from przepisnik.core.models import Ingredient, RecipeDraft, VariantData, VariantKind


def test_approved_variant_switches_steps_and_shows_red_notice(
    page: Page, app_url: str, recipe_data: Path
) -> None:
    """Persist separate instructions and switch them together with ingredient amounts."""
    female = RecipeDraft(
        title="Different variant steps",
        steps=["Prepare female portion."],
        variant=VariantData(ingredients=[Ingredient(name="Rice", amount=100, unit="g")]),
    )
    male = female.model_copy(
        update={
            "steps": ["Prepare male portion."],
            "variant": VariantData(ingredients=[Ingredient(name="Rice", amount=200, unit="g")]),
        }
    )
    with SqliteStore(recipe_data) as store:
        importer = RecipeImporter(store, store)
        origin = SourceRef(parser="respo", name="variants.pdf")
        importer.run([ExtractedRecipe(draft=female)], VariantKind.FEMALE, origin, ImportOptions())
        importer.run(
            [ExtractedRecipe(draft=male)],
            VariantKind.MALE,
            origin,
            ImportOptions(allow_variant_differences=True),
        )
    page.goto(app_url)
    page.get_by_role("button", name="Otwórz przepis: Different variant steps", exact=True).click()
    notice = page.locator(".variant-warning")
    expect(notice).to_contain_text("Kroki przygotowania różnią się dla kobiety i mężczyzny")
    expect(notice).to_have_css("color", "rgb(161, 45, 45)")
    page.locator(".variant-tabs").get_by_role("button", name="Kobieta", exact=True).click()
    expect(page.locator(".steps")).to_have_text("Prepare female portion.")
    expect(page.locator(".ingredients")).to_contain_text("100 g")
    page.locator(".variant-tabs").get_by_role("button", name="Mężczyzna", exact=True).click()
    expect(page.locator(".steps")).to_have_text("Prepare male portion.")
    expect(page.locator(".ingredients")).to_contain_text("200 g")
    expect(notice).to_contain_text("Mężczyzna")
    page.locator(".variant-tabs").get_by_role("button", name="Kobieta", exact=True).click()
    expect(page.locator(".steps")).to_have_text("Prepare female portion.")


def test_matching_steps_do_not_show_different_steps_notice(app_page: Page) -> None:
    """Show the red notice only when both variants actually differ in preparation."""
    page = app_page
    page.get_by_role("button", name="Otwórz przepis: Bajgiel z", exact=False).click()
    expect(page.locator(".variant-warning")).to_have_count(0)
