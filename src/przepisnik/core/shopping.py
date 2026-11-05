"""Validated shared shopping list stored independently of recipe documents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, field_validator

from przepisnik.core.database import SqliteStore
from przepisnik.errors import StoreError

STATE_KEY = "shopping-list"


class ShoppingItem(BaseModel):
    """Editable product quantity and its checked state."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    name: str = Field(min_length=1, max_length=160)
    amount: NonNegativeFloat | None = None
    unit: str = Field(default="", max_length=24)
    checked: bool = False
    source: str = Field(default="", max_length=300)

    @field_validator("name", "unit", "source", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        """Normalize surrounding whitespace before validating lengths."""
        return value.strip() if isinstance(value, str) else value


class ShoppingList(BaseModel):
    """Revisioned collection preventing lost updates from other devices."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    revision: int = Field(default=0, ge=0)
    items: list[ShoppingItem] = Field(default_factory=list, max_length=1000)

    @field_validator("items")
    @classmethod
    def unique_ids(cls, items: list[ShoppingItem]) -> list[ShoppingItem]:
        """Reject ambiguous item identifiers."""
        if len({item.id for item in items}) != len(items):
            raise ValueError("Shopping item IDs must be unique")
        return items


class ShoppingConflictError(StoreError):
    """The list was changed after the client last loaded it."""


def load_shopping_list(store: SqliteStore) -> ShoppingList:
    """Load the shared list, returning an empty revision before its first save."""
    value = store.get_state(STATE_KEY)
    return ShoppingList.model_validate_json(value) if value is not None else ShoppingList()


def save_shopping_list(store: SqliteStore, proposed: ShoppingList) -> ShoppingList:
    """Save inside the caller's transaction, refusing stale revisions and no-ops."""
    current = load_shopping_list(store)
    if proposed.revision != current.revision:
        raise ShoppingConflictError("Shopping list changed; reload before saving")
    if proposed.items == current.items:
        return current
    saved = proposed.model_copy(update={"revision": current.revision + 1})
    store.set_state(STATE_KEY, saved.model_dump_json())
    return saved
