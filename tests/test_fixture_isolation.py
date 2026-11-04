"""Check that recipe mutations stay in each test's disposable database."""

from pathlib import Path

import pytest

from przepisnik.core.database import SqliteStore
from przepisnik.core.recipes import update_metadata


@pytest.mark.parametrize("favorite", [True, False])
def test_recipe_data_starts_fresh(recipe_data: Path, favorite: bool) -> None:
    """Start from fixture state even when another case leaves a changed favorite."""
    recipe_id = "bajgiel-z-domowym-twarozkiem"
    with SqliteStore(recipe_data) as store:
        recipe = store.get(recipe_id)
        assert recipe is not None
        assert recipe.user.favorite is False
        update_metadata(store, recipe_id, {"favorite": favorite})
    with SqliteStore(recipe_data, read_only=True) as store:
        recipe = store.get(recipe_id)
        assert recipe is not None
        assert recipe.user.favorite is favorite
    # Deliberately leave the changed state in this test's database.
