"""Exercise display-only shared recipes through the real HTTP handler."""

import json
from contextlib import closing
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Ingredient, Recipe, Variant, VariantKind


@pytest.mark.parametrize("different_steps", [False, True])
def test_shared_detail_and_listing_never_write_recipe_data(
    recipe_data: Path, app_url: str, different_steps: bool
) -> None:
    """Expose a transient shared variant while preserving the stored document.

    Args:
        recipe_data: Disposable collection used by this test's HTTP server.
        app_url: Address of the real isolated application handler.
        different_steps: Whether the male instructions prevent combination.

    Returns:
        None: API filtering, availability and read-only behavior are verified.
    """
    recipe = Recipe(
        id="api-shared",
        title="API shared",
        steps=["Cook."],
        variants={
            VariantKind.FEMALE: Variant(ingredients=[Ingredient(name="Rice", amount=60, unit="g")]),
            VariantKind.MALE: Variant(
                ingredients=[Ingredient(name="Rice", amount=100, unit="g")],
                steps=["Bake."] if different_steps else None,
            ),
        },
    )
    with SqliteStore(recipe_data) as store, store.transaction():
        saved = store.save(recipe)
    before = (recipe_data / "recipes.sqlite3").read_bytes()
    with closing(HTTPConnection(urlsplit(app_url).netloc, timeout=5)) as client:
        client.request("GET", "/api/recipes/api-shared")
        response = client.getresponse()
        assert response.status == HTTPStatus.OK
        detail = json.loads(response.read())
        assert set(detail["variants"]) == {"female", "male"}
        if different_steps:
            assert detail["combined_variant"] is None
        else:
            assert detail["combined_variant"]["servings"] == 2
            assert detail["combined_variant"]["ingredients"][0]["amount"] == 160
        client.request("GET", "/api/recipes?variant=combined&q=API")
        response = client.getresponse()
        assert response.status == HTTPStatus.OK
        assert [item["id"] for item in json.loads(response.read())["items"]] == [saved.id]
        client.request("GET", "/api/recipes?variant=invalid")
        response = client.getresponse()
        assert response.status == HTTPStatus.BAD_REQUEST
        response.read()
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(saved.id) == saved
    assert (recipe_data / "recipes.sqlite3").read_bytes() == before
