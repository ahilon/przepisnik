"""Check reversible recipe visibility filtering without deleting content."""

import json
from pathlib import Path

import pytest

from przepisnik.cli import main
from przepisnik.core.database import SqliteStore
from przepisnik.core.models import UserMetadata
from przepisnik.core.recipes import RecipeFilters, select_recipes, update_metadata


def test_hidden_recipes_only_appear_in_explicit_hidden_queries(recipe_data: Path) -> None:
    """Exclude hidden recipes from default, favorite, search and uncategorized lists."""
    recipe_id = "bajgiel-z-domowym-twarozkiem"
    with SqliteStore(recipe_data) as store:
        original = store.get(recipe_id)
        assert original is not None
        hidden = update_metadata(
            store,
            recipe_id,
            {"hidden": True, "favorite": True, "meal_types": [], "tags": ["secret"]},
        )
        recipes = store.all()
        for filters in [
            RecipeFilters(),
            RecipeFilters(favorite=True),
            RecipeFilters(uncategorized=True),
            RecipeFilters(query=hidden.title),
            RecipeFilters(tag="secret"),
        ]:
            assert recipe_id not in {recipe.id for recipe in select_recipes(recipes, filters)}
        assert select_recipes(recipes, RecipeFilters(hidden=True)) == [hidden]
        restored = update_metadata(store, recipe_id, {"hidden": False})
        assert restored.user.favorite is True
        assert restored.variants == original.variants
        assert restored.steps == original.steps
        assert recipe_id in {recipe.id for recipe in select_recipes(store.all(), RecipeFilters())}


def test_existing_metadata_defaults_to_visible() -> None:
    """Load existing documents without rewriting their metadata or schema."""
    assert UserMetadata.model_validate({"favorite": True}).hidden is False


def test_cli_lists_hidden_recipes_only_when_requested(
    recipe_data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep hidden recipes discoverable by CLI through its explicit filter."""
    recipe_id = "bajgiel-z-domowym-twarozkiem"
    with SqliteStore(recipe_data) as store:
        update_metadata(store, recipe_id, {"hidden": True})
    args = ["--data-dir", str(recipe_data), "recipes", "list"]
    assert main(args) == 0
    assert recipe_id not in {recipe["id"] for recipe in json.loads(capsys.readouterr().out)}
    assert main([*args, "--hidden"]) == 0
    assert [recipe["id"] for recipe in json.loads(capsys.readouterr().out)] == [recipe_id]
