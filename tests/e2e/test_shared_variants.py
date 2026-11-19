"""Exercise explicit variant collapse and editable audience copies through the UI."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from ui_actions import ApplicationActions

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Recipe, VariantKind


@pytest.fixture
def merge_page(page: Page, app_url: str, shared_recipe: Recipe) -> Page:
    """Open the controlled matching pair after its data is persisted.

    Args:
        page: Fresh Playwright page.
        app_url: Address of this test's isolated application.
        shared_recipe: Matching audience pair saved in disposable data.

    Returns:
        Page: Recipe details displaying the manual merge offer.
    """
    page.goto(app_url)
    ApplicationActions(page).open_recipe(shared_recipe.title)
    return page


def test_manual_merge_persists_one_unscaled_shared_variant(
    merge_page: Page, recipe_data: Path, shared_recipe: Recipe
) -> None:
    """Offer merging without changing data until the user explicitly accepts.

    Args:
        merge_page: Browser displaying the stored matching pair.
        recipe_data: Disposable database and image directory.
        shared_recipe: Original matching pair with metadata and distinct source references.

    Returns:
        None: One unscaled shared variant and its original metadata survive a reload.
    """
    page = merge_page
    app = ApplicationActions(page)
    notice = page.locator(".variant-merge-notice")
    expect(notice).to_contain_text("Warianty kobiety i mężczyzny są identyczne")
    expect(notice.get_by_role("button", name="Złącz", exact=True)).to_be_visible()
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(shared_recipe.id) == shared_recipe
    app.merge_variants()
    expect(page.locator(".variant-tabs button")).to_have_count(1)
    expect(page.locator(".variant-tabs").get_by_role("button", name="Wspólne")).to_be_visible()
    expect(page.locator(".ingredients")).to_contain_text("Merge rice — 100 g")
    expect(page.get_by_label("Liczba porcji", exact=True)).to_have_value("1")
    expect(notice).to_have_count(0)
    page.reload()
    app.open_recipe(shared_recipe.title)
    expect(page.locator(".variant-tabs button")).to_have_count(1)
    expect(page.locator(".source")).to_contain_text(["female-demo.txt", "male-demo.txt"])
    with SqliteStore(recipe_data, read_only=True) as store:
        saved = store.get(shared_recipe.id)
        assert saved is not None
        assert set(saved.variants) == {VariantKind.FAMILY}
        assert saved.user == shared_recipe.user
        assert saved.image == shared_recipe.image
    return None


@pytest.mark.parametrize("difference", ["quantity", "existing-shared"])
def test_conflicting_content_does_not_offer_a_merge(
    page: Page, app_url: str, recipe_data: Path, shared_recipe: Recipe, difference: str
) -> None:
    """Keep audience variants separate when quantities or an existing shared portion differ.

    Args:
        page: Fresh browser page.
        app_url: Isolated application address.
        recipe_data: Disposable recipe directory.
        shared_recipe: Original pair whose source data is varied.
        difference: Conflict preventing safe deduplication.

    Returns:
        None: The UI offers no merge and leaves stored variants unchanged.
    """
    variants = dict(shared_recipe.variants)
    kind = VariantKind.MALE if difference == "quantity" else VariantKind.FAMILY
    base = variants[VariantKind.MALE]
    ingredients = [
        item.model_copy(update={"amount": 101}) if item.name == "Merge rice" else item
        for item in base.ingredients
    ]
    variants[kind] = base.model_copy(update={"ingredients": ingredients})
    with SqliteStore(recipe_data) as store, store.transaction():
        saved = store.save(shared_recipe.model_copy(update={"variants": variants}))
    page.goto(app_url)
    ApplicationActions(page).open_recipe(saved.title)
    expect(page.locator(".variant-merge-notice")).to_have_count(0)
    expect(page.locator(".variant-tabs").get_by_role("button", name="Kobieta")).to_be_visible()
    expect(page.locator(".variant-tabs").get_by_role("button", name="Mężczyzna")).to_be_visible()
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(saved.id) == saved
    return None


@pytest.mark.parametrize(
    "audiences",
    [
        (VariantKind.FAMILY, VariantKind.FEMALE),
        (VariantKind.FAMILY, VariantKind.MALE),
        (VariantKind.FEMALE, VariantKind.MALE),
        (VariantKind.MALE, VariantKind.FEMALE),
    ],
)
def test_add_missing_variant_copies_unsaved_editor_values(
    page: Page,
    app_url: str,
    recipe_data: Path,
    shared_recipe: Recipe,
    audiences: tuple[VariantKind, VariantKind],
) -> None:
    """Copy current amounts and steps into a new editable variant and persist both.

    Args:
        page: Fresh browser page.
        app_url: Isolated application address.
        recipe_data: Disposable database directory.
        shared_recipe: Controlled source recipe whose one audience is retained.
        audiences: Existing source and missing target audience.

    Returns:
        None: Both saved variants retain independent amounts and the copied edited steps.
    """
    source, target = audiences
    base = shared_recipe.variants[VariantKind.FEMALE]
    with SqliteStore(recipe_data) as store, store.transaction():
        store.save(shared_recipe.model_copy(update={"variants": {source: base}}))
    page.goto(app_url)
    app = ApplicationActions(page)
    app.open_recipe(shared_recipe.title)
    app.open_editor()
    source_fields = page.locator(f'#editor [data-kind="{source.value}"]')
    source_fields.locator('[data-field="amount"]').first.fill("125")
    source_fields.locator(".step-editor textarea").first.fill("An edited instruction.")
    app.add_variant(target, source)
    target_fields = page.locator(f'#editor [data-kind="{target.value}"]')
    expect(target_fields.locator('[data-field="amount"]').first).to_have_value("125")
    expect(target_fields.locator(".step-editor textarea").first).to_have_value(
        "An edited instruction."
    )
    expect(page.get_by_role("button", name=f"+ Dodaj wariant: {target.label}")).to_be_hidden()
    target_fields.locator('[data-field="amount"]').first.fill("150")
    app.save_recipe()
    page.reload()
    app.open_recipe(shared_recipe.title)
    app.open_editor()
    expect(page.locator(".editor-variant")).to_have_count(2)
    expect(source_fields.locator('[data-field="amount"]').first).to_have_value("125")
    expect(target_fields.locator('[data-field="amount"]').first).to_have_value("150")
    with SqliteStore(recipe_data, read_only=True) as store:
        saved = store.get(shared_recipe.id)
        assert saved is not None
        assert set(saved.variants) == {source, target}
        assert saved.variants[source].ingredients[0].amount == 125
        assert saved.variants[target].ingredients[0].amount == 150
        assert saved.steps_for(source)[0] == "An edited instruction."
        assert saved.steps_for(target)[0] == "An edited instruction."
    return None


def test_removing_unsaved_copy_and_cancelling_preserves_originals(
    merge_page: Page, recipe_data: Path, shared_recipe: Recipe
) -> None:
    """Discard copied variants and dirty source fields when the editor is cancelled.

    Args:
        merge_page: Browser displaying the original pair.
        recipe_data: Disposable database directory.
        shared_recipe: Stored data that must remain unchanged.

    Returns:
        None: Removed copies can be added again, and cancelling commits no changes.
    """
    page = merge_page
    app = ApplicationActions(page)
    app.open_editor()
    app.add_variant(VariantKind.FAMILY, VariantKind.FEMALE)
    page.get_by_role("button", name="Usuń dodawany wariant: Wspólne", exact=True).click()
    expect(page.locator('#editor [data-kind="family"]')).to_have_count(0)
    app.add_variant(VariantKind.FAMILY, VariantKind.FEMALE)
    page.locator('#editor [data-kind="female"] [data-field="amount"]').first.fill("125")
    page.get_by_role("button", name="Anuluj", exact=True).click()
    expect(page.locator("#editor")).to_be_hidden()
    page.reload()
    app.open_recipe(shared_recipe.title)
    expect(page.locator(".variant-merge-notice")).to_be_visible()
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(shared_recipe.id) == shared_recipe
    return None
