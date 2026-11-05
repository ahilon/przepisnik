"""Validate shared shopping persistence, no-op saves and concurrent updates."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from przepisnik.core.database import SqliteStore
from przepisnik.core.shopping import (
    ShoppingConflictError,
    ShoppingItem,
    ShoppingList,
    load_shopping_list,
    save_shopping_list,
)


def test_list_persists_without_changing_recipes(recipe_data: Path) -> None:
    """Store shared products independently of recipe content and timestamps."""
    with SqliteStore(recipe_data) as store:
        original = store.all()
        assert load_shopping_list(store) == ShoppingList()
        with store.transaction():
            saved = save_shopping_list(
                store,
                ShoppingList(items=[ShoppingItem(id="rice", name=" Rice ", amount=500, unit="g")]),
            )
    with SqliteStore(recipe_data, read_only=True) as store:
        assert load_shopping_list(store) == saved
        assert store.all() == original
    assert saved.revision == 1
    assert saved.items[0].name == "Rice"


def test_unchanged_list_does_not_write_database(recipe_data: Path) -> None:
    """Repeated saves preserve both revision and database bytes."""
    with SqliteStore(recipe_data) as store, store.transaction():
        saved = save_shopping_list(
            store, ShoppingList(items=[ShoppingItem(id="rice", name="Rice", amount=0)])
        )
    snapshot = (recipe_data / "recipes.sqlite3").read_bytes()
    with SqliteStore(recipe_data) as store, store.transaction():
        assert save_shopping_list(store, saved) == saved
    assert (recipe_data / "recipes.sqlite3").read_bytes() == snapshot


def test_stale_list_is_rejected(recipe_data: Path) -> None:
    """An old device cannot overwrite newer edits."""
    with SqliteStore(recipe_data) as store, store.transaction():
        saved = save_shopping_list(store, ShoppingList(items=[ShoppingItem(id="a", name="A")]))
    with SqliteStore(recipe_data) as store, store.transaction():
        with pytest.raises(ShoppingConflictError):
            save_shopping_list(store, ShoppingList(items=[ShoppingItem(id="b", name="B")]))
        assert load_shopping_list(store) == saved


@pytest.mark.parametrize("amount", [-1, float("nan"), float("inf")])
def test_invalid_quantities_are_rejected(amount: float) -> None:
    """Reject negative and non-finite quantities."""
    with pytest.raises(ValidationError):
        ShoppingItem(id="rice", name="Rice", amount=amount)


def test_duplicate_identifiers_and_blank_names_are_rejected() -> None:
    """Keep item addressing unambiguous and product names useful."""
    with pytest.raises(ValidationError):
        ShoppingItem(id="empty", name="   ")
    item = ShoppingItem(id="rice", name="Rice")
    with pytest.raises(ValidationError, match="unique"):
        ShoppingList(items=[item, item])
