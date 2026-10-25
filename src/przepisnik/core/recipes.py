"""Shared application operations for skills, CLI and future web handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from przepisnik.core.models import DishType, MealType, Recipe, UserMetadata, VariantKind, slugify
from przepisnik.errors import StoreError

if TYPE_CHECKING:
    from datetime import datetime

    from przepisnik.core.database import SqliteStore


@dataclass(frozen=True, slots=True)
class RecipeFilters:
    """Combined list filters shared by CLI and UI."""

    query: str = ""
    meal: MealType | None = None
    dish: DishType | None = None
    variant: VariantKind | None = None
    favorite: bool = False


def select_recipes(recipes: list[Recipe], filters: RecipeFilters) -> list[Recipe]:
    """Apply combined filters to current effective categories and ingredient names."""
    needle = slugify(filters.query)
    return [
        recipe
        for recipe in recipes
        if (filters.meal is None or filters.meal in recipe.effective_meal_types)
        and (filters.dish is None or filters.dish in recipe.effective_dish_types)
        and (filters.variant is None or filters.variant in recipe.variants)
        and (not filters.favorite or recipe.user.favorite)
        and (
            not needle
            or needle in slugify(recipe.title)
            or any(
                needle in slugify(i.name) for v in recipe.variants.values() for i in v.ingredients
            )
        )
    ]


def update_metadata(
    store: SqliteStore,
    recipe_id: str,
    patch: dict[str, object],
    *,
    expected_updated_at: datetime | None = None,
) -> Recipe:
    """Validate and atomically update only user-owned fields."""
    with store.transaction():
        recipe = _editable(store, recipe_id, expected_updated_at)
        metadata = UserMetadata.model_validate({**recipe.user.model_dump(), **patch})
        if metadata == recipe.user:
            return recipe
        return store.save(recipe.model_copy(update={"user": metadata}))


def transfer_variant(
    store: SqliteStore,
    recipe_id: str,
    assignment: tuple[VariantKind, VariantKind],
    *,
    copy: bool = False,
    expected_updated_at: datetime | None = None,
) -> Recipe:
    """Move or copy a variant without scaling or overwriting a destination.

    Source provenance and original import receipts are deliberately retained.
    """
    source, target = assignment
    if source == target:
        raise StoreError("Source and target variants must differ")
    with store.transaction():
        recipe = _editable(store, recipe_id, expected_updated_at)
        if source not in recipe.variants:
            raise StoreError(f"Missing source variant: {source}")
        if target in recipe.variants:
            raise StoreError(f"Target variant already exists: {target}; compare before changing")
        variants = dict(recipe.variants)
        variants[target] = variants[source]
        if not copy:
            del variants[source]
        return store.save(recipe.model_copy(update={"variants": variants}))


def _editable(store: SqliteStore, recipe_id: str, expected: datetime | None) -> Recipe:
    recipe = store.get(recipe_id)
    if recipe is None:
        raise StoreError(f"Unknown recipe: {recipe_id}")
    if expected is not None and recipe.updated_at != expected:
        raise StoreError("Recipe changed since it was opened; reload before saving")
    return recipe
