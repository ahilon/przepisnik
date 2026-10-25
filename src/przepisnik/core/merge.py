"""Pure logic deciding where an extracted recipe belongs and how it changes the store."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from przepisnik.core.models import (
    Recipe,
    RecipeDraft,
    Source,
    Variant,
    VariantKind,
    recipe_id_for,
    slugify,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

SAME_RECIPE_MIN_OVERLAP = 0.5


class MergeOutcome(StrEnum):
    """What happened to the store after a merge."""

    CREATED = "created"
    NEW_VERSION = "new_version"
    VARIANT_ADDED = "variant_added"
    UNCHANGED = "unchanged"
    REPLACED = "replaced"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Merge outcome with the resulting recipe (the existing one when nothing changed)."""

    outcome: MergeOutcome
    recipe: Recipe
    reason: str | None = None


def merge_variant(
    versions: Sequence[Recipe],
    draft: RecipeDraft,
    kind: VariantKind,
    source: Source | None,
    *,
    replace: bool = False,
) -> MergeResult:
    """Merge a recipe draft as variant ``kind`` into the stored versions of its title.

    The draft joins the first version whose ingredients overlap enough; otherwise it
    becomes a new version. Stored variant data is never silently overwritten: differing
    data is reported as a conflict unless ``replace`` is set.

    Args:
        versions: Stored recipes with the same title slug, ordered by version.
        draft: Newly extracted recipe.
        kind: Variant the draft represents.
        source: Provenance of the draft.
        replace: Overwrite a differing variant of the same kind.

    Returns:
        The merge outcome and resulting recipe.
    """
    target = next((recipe for recipe in versions if _is_same_recipe(recipe, draft)), None)
    if target is None:
        version = max((recipe.version for recipe in versions), default=0) + 1
        outcome = MergeOutcome.CREATED if version == 1 else MergeOutcome.NEW_VERSION
        variant = _variant(draft, source, recipe_steps=draft.steps)
        return MergeResult(outcome, _new_recipe(draft, kind, variant, version))

    variant = _variant(draft, source, recipe_steps=target.steps)
    current = target.variants.get(kind)
    if current is not None:
        if _same_content(current, variant):
            return MergeResult(MergeOutcome.UNCHANGED, target)
        if not replace:
            return MergeResult(MergeOutcome.CONFLICT, target, "variant data differs")

    updated = target.model_copy(
        update={
            "variants": {**target.variants, kind: variant},
            "notes": list(dict.fromkeys([*target.notes, *draft.notes])),
            "suggested_batch_portions": draft.suggested_batch_portions
            or target.suggested_batch_portions,
        }
    )
    outcome = MergeOutcome.VARIANT_ADDED if current is None else MergeOutcome.REPLACED
    return MergeResult(outcome, updated)


def ingredient_overlap(recipe: Recipe, draft: RecipeDraft) -> float:
    """Return the Jaccard similarity of ingredient names (0.0 - 1.0)."""
    stored = _names(i.name for v in recipe.variants.values() for i in v.ingredients)
    incoming = _names(i.name for i in draft.variant.ingredients)
    union = stored | incoming
    return len(stored & incoming) / len(union) if union else 0.0


def _is_same_recipe(recipe: Recipe, draft: RecipeDraft) -> bool:
    return ingredient_overlap(recipe, draft) >= SAME_RECIPE_MIN_OVERLAP


def _names(names: Iterable[str]) -> set[str]:
    return {slugify(name) for name in names}


def _variant(draft: RecipeDraft, source: Source | None, recipe_steps: list[str]) -> Variant:
    own_steps = None if draft.steps == recipe_steps else draft.steps
    return Variant(**dict(draft.variant), steps=own_steps, source=source)


def _new_recipe(draft: RecipeDraft, kind: VariantKind, variant: Variant, version: int) -> Recipe:
    return Recipe(
        id=recipe_id_for(draft.title, version),
        title=draft.title,
        version=version,
        steps=draft.steps,
        notes=draft.notes,
        suggested_batch_portions=draft.suggested_batch_portions,
        variants={kind: variant},
    )


def _same_content(left: Variant, right: Variant) -> bool:
    return left.model_dump(exclude={"source"}) == right.model_dump(exclude={"source"})
