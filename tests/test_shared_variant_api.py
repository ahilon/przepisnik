"""Check persistent variant merging, optimistic conflicts and transactional rollback."""

import json
from contextlib import closing
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path
from typing import cast
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Ingredient, Recipe, VariantKind
from przepisnik.core.shared_variants import SHARED_SOURCES_STATE_PREFIX
from przepisnik.errors import StoreError


class RecipeClient:
    """Send JSON requests to this test's real isolated HTTP server."""

    def __init__(self, app_url: str) -> None:
        """Retain the dynamic address supplied by the application fixture.

        Args:
            app_url: Base URL of this test's disposable application instance.

        Returns:
            None: Stores the authority and valid browser origin.
        """
        self._authority = urlsplit(app_url).netloc
        self._origin = app_url
        return None

    def request(
        self, method: str, path: str, payload: object = None, origin: str | None = None
    ) -> tuple[int, dict[str, object]]:
        """Send a request and consume the entire JSON response before closing.

        Args:
            method: HTTP method used by the scenario.
            path: Application-relative endpoint.
            payload: JSON body for write requests.
            origin: Explicit origin for security scenarios, or the valid local origin.

        Returns:
            tuple[int, dict[str, object]]: HTTP status and decoded response object.
        """
        headers = {"Content-Type": "application/json", "Origin": origin or self._origin}
        body = json.dumps(payload) if method == "POST" else None
        with closing(HTTPConnection(self._authority, timeout=5)) as connection:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, cast(dict[str, object], json.loads(response.read()))


@pytest.fixture
def api(app_url: str) -> RecipeClient:
    """Provide a client for the isolated real application handler.

    Args:
        app_url: Dynamic loopback URL supplied by the server fixture.

    Returns:
        RecipeClient: JSON client requiring no fixed port or external service.
    """
    return RecipeClient(app_url)


def test_merge_capability_read_does_not_change_data(
    api: RecipeClient, recipe_data: Path, shared_recipe: Recipe
) -> None:
    """Advertise manual merging without modifying matching variants on a read.

    Args:
        api: Client connected to the isolated application.
        recipe_data: Disposable database and photo directory.
        shared_recipe: Stored compatible audience pair.

    Returns:
        None: Eligibility is true while original records and database bytes remain unchanged.
    """
    before = (recipe_data / "recipes.sqlite3").read_bytes()
    status, detail = api.request("GET", f"/api/recipes/{shared_recipe.id}")
    assert status == HTTPStatus.OK
    assert detail["can_merge_variants"] is True
    assert set(cast(dict[str, object], detail["variants"])) == {"female", "male"}
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(shared_recipe.id) == shared_recipe
    assert (recipe_data / "recipes.sqlite3").read_bytes() == before
    return None


def test_merge_persists_one_unscaled_variant_and_both_sources(
    api: RecipeClient, recipe_data: Path, shared_recipe: Recipe
) -> None:
    """Retain recipe metadata, photo bytes and provenance across the merge transaction.

    Args:
        api: Client connected to the isolated application.
        recipe_data: Disposable database and photo directory.
        shared_recipe: Stored compatible pair with a real local image.

    Returns:
        None: Reloaded data contains one shared variant and both original source references.
    """
    photo = recipe_data / "recipes" / shared_recipe.id / str(shared_recipe.image)
    before_photo = photo.read_bytes()
    token = shared_recipe.model_dump(mode="json")["updated_at"]
    status, result = api.request(
        "POST", f"/api/recipes/{shared_recipe.id}/merge-variants", {"updated_at": token}
    )
    assert status == HTTPStatus.OK
    assert result == {"id": shared_recipe.id, "changed": True}
    with SqliteStore(recipe_data, read_only=True) as store:
        saved = store.get(shared_recipe.id)
        assert saved is not None
        assert set(saved.variants) == {VariantKind.FAMILY}
        assert saved.variants[VariantKind.FAMILY].ingredients[0].amount == 100
        assert saved.model_dump(exclude={"variants", "updated_at"}) == shared_recipe.model_dump(
            exclude={"variants", "updated_at"}
        )
        references = json.loads(store.get_state(f"{SHARED_SOURCES_STATE_PREFIX}{saved.id}") or "[]")
        assert {source["file"] for source in references} == {"female-demo.txt", "male-demo.txt"}
    status, detail = api.request("GET", f"/api/recipes/{shared_recipe.id}")
    assert status == HTTPStatus.OK
    assert detail["can_merge_variants"] is False
    assert detail["combined_variant"] is None
    assert set(cast(dict[str, object], detail["variants"])) == {"family"}
    assert len(cast(list[object], detail["shared_sources"])) == 2
    assert photo.read_bytes() == before_photo
    before_retry = (recipe_data / "recipes.sqlite3").read_bytes()
    status, _ = api.request(
        "POST", f"/api/recipes/{shared_recipe.id}/merge-variants", {"updated_at": token}
    )
    assert status == HTTPStatus.CONFLICT
    assert (recipe_data / "recipes.sqlite3").read_bytes() == before_retry
    return None


@pytest.mark.parametrize(
    "failure", ["stale", "missing-token", "extra-field", "origin", "different"]
)
def test_rejected_merge_preserves_current_recipe(
    api: RecipeClient, recipe_data: Path, shared_recipe: Recipe, failure: str
) -> None:
    """Reject stale, malformed, forbidden and incompatible merge requests without writes.

    Args:
        api: Client connected to the isolated application.
        recipe_data: Disposable database and photo directory.
        shared_recipe: Stored pair used as the initial state.
        failure: Independent reason the request must not be accepted.

    Returns:
        None: Failed requests preserve the current recipe and do not create source history.
    """
    original = shared_recipe
    token = original.model_dump(mode="json")["updated_at"]
    payload: dict[str, object] = {"updated_at": token}
    expected = HTTPStatus.CONFLICT
    origin = None
    if failure in {"stale", "different"}:
        changes: dict[str, object] = {"title": "Updated on another device"}
        if failure == "different":
            male = original.variants[VariantKind.MALE].model_copy(
                update={"ingredients": [Ingredient(name="Different ingredient")]}
            )
            changes = {"variants": {**original.variants, VariantKind.MALE: male}}
        with SqliteStore(recipe_data) as store, store.transaction():
            original = store.save(original.model_copy(update=changes))
        if failure == "different":
            payload["updated_at"] = original.model_dump(mode="json")["updated_at"]
    elif failure == "missing-token":
        payload = {}
        expected = HTTPStatus.BAD_REQUEST
    elif failure == "extra-field":
        payload["variants"] = {}
        expected = HTTPStatus.BAD_REQUEST
    else:
        origin = "https://example.invalid"
        expected = HTTPStatus.FORBIDDEN
    before = (recipe_data / "recipes.sqlite3").read_bytes()
    status, _ = api.request(
        "POST", f"/api/recipes/{original.id}/merge-variants", payload, origin=origin
    )
    assert status == expected
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(original.id) == original
        assert store.get_state(f"{SHARED_SOURCES_STATE_PREFIX}{original.id}") is None
    assert (recipe_data / "recipes.sqlite3").read_bytes() == before
    return None


def test_merge_transaction_rolls_back_if_source_history_cannot_be_saved(
    api: RecipeClient, recipe_data: Path, shared_recipe: Recipe
) -> None:
    """Roll back recipe replacement when its dependent provenance write fails.

    Args:
        api: Client connected to the isolated application.
        recipe_data: Disposable database and photo directory.
        shared_recipe: Original matching pair that must survive the failed transaction.

    Returns:
        None: Neither the recipe nor source history is partially committed.
    """
    with patch.object(SqliteStore, "set_state", side_effect=StoreError("Synthetic write failure")):
        status, _ = api.request(
            "POST",
            f"/api/recipes/{shared_recipe.id}/merge-variants",
            {"updated_at": shared_recipe.model_dump(mode="json")["updated_at"]},
        )
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(shared_recipe.id) == shared_recipe
        assert store.get_state(f"{SHARED_SOURCES_STATE_PREFIX}{shared_recipe.id}") is None
    return None


def test_existing_shared_recipe_exposes_its_source_without_a_merge(
    api: RecipeClient, recipe_data: Path, shared_recipe: Recipe
) -> None:
    """Keep existing family-only records and their provenance readable.

    Args:
        api: Client connected to the isolated application.
        recipe_data: Disposable database directory.
        shared_recipe: Source record used to create a pre-existing shared variant.

    Returns:
        None: Existing shared quantities and source references require no migration or write.
    """
    shared = shared_recipe.variants[VariantKind.FEMALE]
    with SqliteStore(recipe_data) as store, store.transaction():
        original = store.save(
            shared_recipe.model_copy(update={"variants": {VariantKind.FAMILY: shared}})
        )
    before = (recipe_data / "recipes.sqlite3").read_bytes()
    status, detail = api.request("GET", f"/api/recipes/{original.id}")
    assert status == HTTPStatus.OK
    assert detail["can_merge_variants"] is False
    assert shared.source is not None
    assert detail["shared_sources"] == [shared.source.model_dump(mode="json")]
    assert (recipe_data / "recipes.sqlite3").read_bytes() == before
    return None


def test_unknown_recipe_merge_returns_not_found(api: RecipeClient) -> None:
    """Return a missing-resource response without creating a replacement recipe.

    Args:
        api: Client connected to an isolated application with no matching recipe.

    Returns:
        None: The server reports the requested recipe is absent.
    """
    status, _ = api.request("POST", "/api/recipes/missing/merge-variants", {"updated_at": None})
    assert status == HTTPStatus.NOT_FOUND
    return None
