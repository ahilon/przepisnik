"""Verify nutrition estimates through the local API with an offline provider transport."""

import json
from http import HTTPStatus
from http.client import HTTPResponse, HTTPSConnection
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from test_shared_variant_api import RecipeClient

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Recipe, VariantKind
from przepisnik.web import nutrition_ai
from przepisnik.web.nutrition_ai import NutritionEstimator, OpenAINutritionEstimator

_ESTIMATE_PATH = "/api/nutrition/estimate"
_INPUT = {
    "servings": 2,
    "ingredients": [{"name": "Ryż", "amount": 120, "unit": "g", "raw": "imported text"}],
}
_TOTALS = {"kcal": 432, "protein_g": 8.4, "fat_g": 0.8, "carbs_g": 96}


@pytest.fixture
def nutrition_estimator(request: pytest.FixtureRequest) -> NutritionEstimator | None:
    """Enable the adapter only for tests opting into the offline transport.

    Args:
        request: Fixture invocation with an optional indirect enable flag.

    Returns:
        A provider adapter with an inert key, or None when no key is configured.
    """
    if not getattr(request, "param", False):
        return None
    return OpenAINutritionEstimator("fixture-placeholder")


@pytest.fixture
def provider_connection(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Intercept outgoing HTTPS before creating any real provider connection.

    Args:
        monkeypatch: Restores the actual transport at the end of the test.

    Returns:
        A connection mock providing a configurable completed provider response.
    """
    response = Mock(spec=HTTPResponse)
    response.status = HTTPStatus.OK
    response.read.return_value = json.dumps(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(_TOTALS)}],
                }
            ],
        }
    ).encode()
    connection = Mock(spec=HTTPSConnection)
    connection.getresponse.return_value = response
    monkeypatch.setattr(nutrition_ai, "HTTPSConnection", Mock(return_value=connection))
    return connection


def test_nutrition_is_unavailable_without_a_key(
    app_url: str, shared_recipe: Recipe, provider_connection: Mock
) -> None:
    """Report the missing capability and reject estimates without any provider call.

    Args:
        app_url: Address of the isolated recipe server.
        shared_recipe: Existing recipe used to open the editor.
        provider_connection: Inert HTTPS connection used to detect unexpected activity.

    Returns:
        None: The detail marks AI unavailable and the endpoint rejects the request.
    """
    api = RecipeClient(app_url)
    status, details = api.request("GET", f"/api/recipes/{shared_recipe.id}")
    assert status == HTTPStatus.OK
    assert details["nutrition_ai_available"] is False
    status, body = api.request("POST", _ESTIMATE_PATH, _INPUT)
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert "api_key" in str(body["error"])
    provider_connection.request.assert_not_called()
    return None


@pytest.mark.parametrize("nutrition_estimator", [True], indirect=True)
def test_estimate_uses_draft_quantities_and_persists_only_on_save(
    app_url: str, shared_recipe: Recipe, recipe_data: Path, provider_connection: Mock
) -> None:
    """Use the edited quantities and persist the four estimates with their provenance.

    Args:
        app_url: Address of the isolated recipe server.
        shared_recipe: Recipe with two saved audience variants.
        recipe_data: The disposable database containing that recipe.
        provider_connection: Recorded offline provider transport.

    Returns:
        None: Only an explicit recipe save changes SQLite, and only one variant changes.
    """
    api = RecipeClient(app_url)
    path = f"/api/recipes/{shared_recipe.id}"
    status, details = api.request("GET", path)
    assert status == HTTPStatus.OK
    assert details["nutrition_ai_available"] is True
    status, estimate = api.request("POST", _ESTIMATE_PATH, _INPUT)
    assert status == HTTPStatus.OK
    assert estimate == _TOTALS
    provider_connection.request.assert_called_once()
    request_body = json.loads(provider_connection.request.call_args.kwargs["body"])
    assert json.loads(request_body["input"]) == {
        "servings": 2,
        "ingredients": [{"name": "Ryż", "amount": 120, "unit": "g"}],
    }
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(shared_recipe.id) == shared_recipe

    variants = cast(dict[str, dict[str, object]], details["variants"])
    variants["female"].update(nutrition=estimate, nutrition_estimated=True)
    status, _ = api.request(
        "POST",
        path,
        {"recipe": {"variants": variants}, "updated_at": details["updated_at"]},
    )
    assert status == HTTPStatus.OK
    with SqliteStore(recipe_data, read_only=True) as store:
        saved = store.get(shared_recipe.id)
    assert saved is not None
    female = saved.variants[VariantKind.FEMALE]
    assert female.nutrition_estimated is True
    assert female.nutrition is not None
    assert female.nutrition.model_dump() == _TOTALS
    assert saved.variants[VariantKind.MALE] == shared_recipe.variants[VariantKind.MALE]
    return None


@pytest.mark.parametrize("nutrition_estimator", [True], indirect=True)
def test_invalid_draft_never_reaches_the_provider(app_url: str, provider_connection: Mock) -> None:
    """Reject incomplete variant quantities locally.

    Args:
        app_url: Address of the isolated recipe server.
        provider_connection: Inert transport used to detect outgoing requests.

    Returns:
        None: No provider request is made for invalid serving counts.
    """
    status, _ = RecipeClient(app_url).request("POST", _ESTIMATE_PATH, {**_INPUT, "servings": 0})
    assert status == HTTPStatus.BAD_REQUEST
    provider_connection.request.assert_not_called()
    return None


@pytest.mark.parametrize("nutrition_estimator", [True], indirect=True)
@pytest.mark.parametrize("failure", ["timeout", "invalid-totals", "quota"])
def test_provider_failure_preserves_saved_recipe(
    app_url: str,
    recipe_data: Path,
    shared_recipe: Recipe,
    provider_connection: Mock,
    failure: str,
) -> None:
    """Report offline provider failures while retaining existing nutrition.

    Args:
        app_url: Address of the isolated recipe server.
        recipe_data: Disposable collection directory.
        shared_recipe: Original stored recipe, including nutrition.
        provider_connection: Transport under control of the test.
        failure: Timeout, incomplete nutrition, or an exhausted provider quota.

    Returns:
        None: The endpoint returns a user-facing failure and SQLite is unchanged.
    """
    if failure == "timeout":
        provider_connection.getresponse.side_effect = TimeoutError
    elif failure == "invalid-totals":
        provider_connection.getresponse.return_value.read.return_value = (
            b'{"status":"completed","output":[{"type":"message",'
            b'"content":[{"type":"output_text","text":"{}"}]}]}'
        )
    else:
        provider_connection.getresponse.return_value.status = HTTPStatus.TOO_MANY_REQUESTS

    status, body = RecipeClient(app_url).request("POST", _ESTIMATE_PATH, _INPUT)
    assert status == HTTPStatus.BAD_GATEWAY
    assert "Spróbuj ponownie" in str(body["error"])
    provider_connection.close.assert_called_once()
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(shared_recipe.id) == shared_recipe
    return None
