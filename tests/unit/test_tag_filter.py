"""Keep tag options available independently of filtered results and pagination."""

from typing import cast
from unittest.mock import Mock, patch

import pytest
from factories import recipe

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import Recipe, UserMetadata
from przepisnik.web import server
from przepisnik.web.server import RecipeHandler


@pytest.fixture
def tagged_recipes() -> list[Recipe]:
    """Build active and hidden recipes with overlapping and distinct tags.

    Returns:
        list[Recipe]: In-memory records with no filesystem or browser dependency.
    """
    return [
        recipe("Fast").model_copy(update={"user": UserMetadata(tags=["Quick", "Dinner"])}),
        recipe("Calm").model_copy(update={"user": UserMetadata(tags=["Family", "Dinner"])}),
        recipe("Hidden").model_copy(update={"user": UserMetadata(hidden=True, tags=["Private"])}),
    ]


def _listing(recipes: list[Recipe], query: dict[str, list[str]]) -> dict[str, object]:
    """Exercise listing logic while replacing only storage and HTTP serialization.

    Args:
        recipes: Stored records returned by the isolated store stub.
        query: Listing filters using the handler's parsed query format.

    Returns:
        dict[str, object]: Response data used to populate the tag dropdown.
    """
    store = Mock(spec=SqliteStore)
    store.all.return_value = recipes
    handler = RecipeHandler.__new__(RecipeHandler)
    with patch.object(handler, "_json") as respond:
        handler._list(cast(SqliteStore, store), query)
    respond.assert_called_once()
    assert respond.call_args is not None
    return cast(dict[str, object], respond.call_args.args[0])


@pytest.mark.parametrize(
    ("query", "expected_total"),
    [
        ({}, 2),
        ({"q": ["no matching recipe"]}, 0),
        ({"tag": ["Quick"]}, 1),
        ({"variant": ["male"]}, 0),
        ({"meal": ["breakfast"]}, 0),
        ({"favorite": ["1"]}, 0),
    ],
)
def test_tag_options_survive_filters_and_empty_results(
    tagged_recipes: list[Recipe], query: dict[str, list[str]], expected_total: int
) -> None:
    """Retain all active collection tags when other controls narrow the recipe list.

    Args:
        tagged_recipes: Active and hidden source records.
        query: Search, tag, variant, meal or favorite selection.
        expected_total: Number of recipes that actually match the filter.

    Returns:
        None: Sorted unique tag options remain available even with no matches.
    """
    payload = _listing(tagged_recipes, query)
    assert payload["total"] == expected_total
    assert payload["tags"] == ["Dinner", "Family", "Quick"]
    return None


@pytest.mark.parametrize(
    ("hidden", "expected_tags"),
    [(False, ["Dinner", "Family", "Quick"]), (True, ["Private"])],
)
def test_tag_options_follow_the_selected_collection(
    tagged_recipes: list[Recipe], hidden: bool, expected_tags: list[str]
) -> None:
    """Keep hidden-only tags separate from the visible collection's options.

    Args:
        tagged_recipes: Active and hidden source records.
        hidden: Whether the hidden collection is selected.
        expected_tags: Tag options belonging to that collection.

    Returns:
        None: Switching collections returns only the appropriate tags.
    """
    query = {"hidden": ["1"]} if hidden else {}
    assert _listing(tagged_recipes, query)["tags"] == expected_tags
    return None


def test_tag_options_include_recipes_on_other_pages(
    tagged_recipes: list[Recipe], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not lose tag choices when the owning recipe is on another page.

    Args:
        tagged_recipes: Active and hidden source records.
        monkeypatch: Fixture limiting each response to one recipe.

    Returns:
        None: The second page retains tags from the whole active collection.
    """
    monkeypatch.setattr(server, "PAGE_SIZE", 1)
    payload = _listing(tagged_recipes, {"page": ["2"]})
    items = cast(list[dict[str, object]], payload["items"])
    assert payload["page"] == 2
    assert [item["id"] for item in items] == [tagged_recipes[0].id]
    assert payload["tags"] == ["Dinner", "Family", "Quick"]
    return None


def test_empty_collection_returns_empty_tag_options() -> None:
    """Represent a collection without tags without inventing or retaining old options.

    Returns:
        None: Empty results contain an explicit empty tag list.
    """
    payload = _listing([], {})
    assert payload["tags"] == []
    assert payload["items"] == []
    assert payload["total"] == 0
    return None
