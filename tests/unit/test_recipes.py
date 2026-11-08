"""Check recipe filtering and validated user-metadata and variant operations."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factories import persist, recipe
from pydantic import ValidationError

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import DishType, MealType, Recipe, UserMetadata, VariantKind
from przepisnik.core.recipes import (
    RecipeFilters,
    select_recipes,
    transfer_variant,
    update_metadata,
)
from przepisnik.errors import StoreError

FEMALE = VariantKind.FEMALE
MALE = VariantKind.MALE


@pytest.fixture
def recipes() -> list[Recipe]:
    """Return a small collection covering every filter dimension."""
    return [
        recipe("Zupa z łososia", names=["Łosoś", "Ziemniaki"]).model_copy(
            update={
                "meal_types": [MealType.LUNCH],
                "dish_types": [DishType.SOUP],
                "user": UserMetadata(favorite=True, tags=["Szybkie"]),
            }
        ),
        recipe("Owsianka", names=["Płatki owsiane"], kinds=(FEMALE, MALE)).model_copy(
            update={"meal_types": [MealType.BREAKFAST]}
        ),
        recipe("Sałatka", names=["Sałata"]).model_copy(
            update={"user": UserMetadata(meal_types=[], dish_types=[DishType.SALAD])}
        ),
        recipe("Ukryty deser", names=["Cukier"]).model_copy(
            update={"user": UserMetadata(hidden=True, favorite=True)}
        ),
    ]


@pytest.mark.parametrize(
    ("filters", "titles"),
    [
        (RecipeFilters(), ["Zupa z łososia", "Owsianka", "Sałatka"]),
        (RecipeFilters(query="LOSOS"), ["Zupa z łososia"]),
        (RecipeFilters(query="platki"), ["Owsianka"]),
        (RecipeFilters(meal=MealType.BREAKFAST), ["Owsianka"]),
        (RecipeFilters(dish=DishType.SALAD), ["Sałatka"]),
        (RecipeFilters(variant=MALE), ["Owsianka"]),
        (RecipeFilters(favorite=True), ["Zupa z łososia"]),
        (RecipeFilters(tag="Szybkie"), ["Zupa z łososia"]),
        (RecipeFilters(uncategorized=True), ["Sałatka"]),
        (RecipeFilters(hidden=True), ["Ukryty deser"]),
        (RecipeFilters(meal=MealType.LUNCH, favorite=True, query="zupa"), ["Zupa z łososia"]),
        (RecipeFilters(meal=MealType.DINNER), []),
    ],
)
def test_select_recipes_combines_filters(
    recipes: list[Recipe], filters: RecipeFilters, titles: list[str]
) -> None:
    """Match effective categories, ingredients, flags and visibility together."""
    assert [item.title for item in select_recipes(recipes, filters)] == titles


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteStore]:
    """Return a store containing one female-only recipe."""
    with SqliteStore(tmp_path) as opened:
        persist(opened, recipe())
        yield opened


def test_update_metadata_changes_only_user_fields(store: SqliteStore) -> None:
    """Persist user edits and skip writes for identical patches."""
    original = store.get("ryz-z-kurczakiem")
    assert original is not None
    updated = update_metadata(store, original.id, {"notes": "Dodać chili", "tags": ["Ostre"]})
    assert updated.user.notes == "Dodać chili"
    assert updated.variants == original.variants
    assert update_metadata(store, original.id, {"notes": "Dodać chili"}) == updated


def test_update_metadata_validates_patch(store: SqliteStore) -> None:
    """Reject invalid user fields without saving."""
    with pytest.raises(ValidationError):
        update_metadata(store, "ryz-z-kurczakiem", {"preparation_minutes": 0})
    with pytest.raises(ValidationError):
        update_metadata(store, "ryz-z-kurczakiem", {"title": "Inny"})


def test_operations_refuse_unknown_or_stale_recipes(store: SqliteStore) -> None:
    """Report missing recipes and edits based on an outdated copy."""
    with pytest.raises(StoreError, match="Unknown recipe"):
        update_metadata(store, "missing", {"favorite": True})
    stale = datetime(2000, 1, 1, tzinfo=UTC)
    with pytest.raises(StoreError, match="changed since"):
        update_metadata(store, "ryz-z-kurczakiem", {"favorite": True}, expected_updated_at=stale)
    with pytest.raises(StoreError, match="changed since"):
        transfer_variant(store, "ryz-z-kurczakiem", (FEMALE, MALE), expected_updated_at=stale)


def test_move_and_copy_variants(store: SqliteStore) -> None:
    """Move removes the source variant; copy keeps it."""
    current = store.get("ryz-z-kurczakiem")
    assert current is not None
    moved = transfer_variant(
        store, current.id, (FEMALE, MALE), expected_updated_at=current.updated_at
    )
    assert list(moved.variants) == [MALE]
    assert moved.variants[MALE] == current.variants[FEMALE]
    copied = transfer_variant(store, current.id, (MALE, VariantKind.FAMILY), copy=True)
    assert set(copied.variants) == {MALE, VariantKind.FAMILY}


@pytest.mark.parametrize(
    ("assignment", "message"),
    [
        ((FEMALE, FEMALE), "must differ"),
        ((MALE, FEMALE), "Missing source"),
    ],
)
def test_invalid_transfers_are_refused(
    store: SqliteStore, assignment: tuple[VariantKind, VariantKind], message: str
) -> None:
    """Never transfer to the same variant or from a missing one."""
    with pytest.raises(StoreError, match=message):
        transfer_variant(store, "ryz-z-kurczakiem", assignment)


def test_transfer_never_overwrites_a_variant(store: SqliteStore) -> None:
    """Require a comparison before replacing an existing destination."""
    transfer_variant(store, "ryz-z-kurczakiem", (FEMALE, MALE), copy=True)
    with pytest.raises(StoreError, match="already exists"):
        transfer_variant(store, "ryz-z-kurczakiem", (FEMALE, MALE))
