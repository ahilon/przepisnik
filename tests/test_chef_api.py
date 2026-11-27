"""Exercise recipe generation through the local HTTP server without paid calls."""

import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_shared_variant_api import RecipeClient

from przepisnik.core.database import SqliteStore
from przepisnik.web import chef

_ORDER = {"mode": "create", "text": "Ryż z pomidorami", "servings": 2}
_CARD = {
    "title": "Ryż z pomidorami",
    "servings": 2,
    "ingredients": [{"name": "Ryż", "amount": 120, "unit": "g", "group": None}],
    "steps": ["Ugotuj ryż i wymieszaj z pomidorami."],
    "meals": [],
    "dishes": [],
    "minutes": 20,
    "source_nutrition": None,
    "kcal_estimate_per_serving": 200,
}


@pytest.fixture
def provider_transport(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Replace the HTTPS constructor before any provider call can leave the process.

    Args:
        monkeypatch: Restores the transport and provider configuration after the test.

    Returns:
        Mock constructor whose connection and response can be configured by each test.
    """
    monkeypatch.delenv(chef.OPENAI_API_KEY_ENV, raising=False)
    transport = Mock()
    transport.return_value.getresponse.return_value.status = HTTPStatus.OK
    monkeypatch.setattr(chef, "HTTPSConnection", transport)
    return transport


def test_generate_preview_and_save_once(
    app_url: str,
    recipe_data: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_transport: Mock,
) -> None:
    """Check provider routing, billing, preview isolation and a retried save.

    Args:
        app_url: Loopback address of the isolated server.
        recipe_data: Disposable database path.
        monkeypatch: Sets isolated server environment values.
        provider_transport: Records the request without a network connection.
    """
    monkeypatch.setenv("openai_api_key", "fixture-placeholder")
    card_json = json.dumps({"status": "recipe", "recipe": _CARD})
    usage = {"input_tokens": 30, "output_tokens": 20}
    response = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": card_json}]}],
        "usage": usage,
    }
    connection = provider_transport.return_value
    connection.getresponse.return_value.read.return_value = json.dumps(response).encode()
    api = RecipeClient(app_url)
    status, preview = api.request("POST", "/api/chef/generate", _ORDER)
    assert status == HTTPStatus.OK
    identity = f"chef-{preview['draft_id']}"
    assert "fixture-placeholder" not in json.dumps(preview)
    method, path, body, headers = connection.request.call_args.args
    assert method == "POST"
    request = json.loads(body)
    provider_transport.assert_called_once_with("api.openai.com", timeout=65)
    assert path == "/v1/responses"
    assert headers["Authorization"] == "Bearer fixture-placeholder"
    assert json.loads(request["input"])["text"] == _ORDER["text"]
    assert request["text"]["format"]["strict"] is True
    status, settings = api.request("GET", "/api/chef")
    assert status == HTTPStatus.OK
    assert settings["enabled"] is True
    assert settings["image_max"] == 20_000
    assert settings["budget"] == {"reserved": 0, "spent": 350, "available": 999_650}
    with SqliteStore(recipe_data, read_only=True) as store:
        assert store.get(identity) is None

    save = {"chef_draft": preview["draft_id"], "recipe": {"title": "Domowy ryż"}}
    status, saved = api.request("POST", "/api/recipes", save)
    assert status == HTTPStatus.CREATED
    assert saved["id"] == identity
    status, retried = api.request("POST", "/api/recipes", save)
    assert status == HTTPStatus.OK
    assert retried == {"id": identity, "changed": False}
    with SqliteStore(recipe_data, read_only=True) as store:
        recipe = store.get(identity)
    assert recipe is not None
    assert recipe.title == "Domowy ryż"
    return None


def test_chef_without_key_does_not_call_provider(app_url: str, provider_transport: Mock) -> None:
    """The local API hides an unconfigured chef and rejects generation.

    Args:
        app_url: Loopback address of the isolated server.
        provider_transport: Detects unexpected provider connections.
    """
    api = RecipeClient(app_url)
    assert api.request("GET", "/api/chef") == (HTTPStatus.OK, {"enabled": False})
    status, _ = api.request("POST", "/api/chef/generate", _ORDER)
    assert status == HTTPStatus.BAD_REQUEST
    provider_transport.assert_not_called()
    return None
