"""Pure, conservative import decisions; existing data is never replaced."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from przepisnik.core.identity import content_fingerprint, draft_fingerprint
from przepisnik.core.models import Recipe, RecipeDraft, Source, Variant, VariantKind, recipe_id_for

if TYPE_CHECKING:
    from collections.abc import Sequence


class MergeOutcome(StrEnum):
    """Result of comparing an incoming recipe with stored data."""

    CREATED = "created"
    VARIANT_ADDED = "variant_added"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Decision and resulting recipe; conflicts retain the stored recipe."""

    outcome: MergeOutcome
    recipe: Recipe
    reason: str | None = None


def merge_variant(
    versions: Sequence[Recipe],
    draft: RecipeDraft,
    kind: VariantKind,
    source: Source | None,
    *,
    allow_variant_differences: bool = False,
) -> MergeResult:
    """Create, skip identical data, or add an unambiguous missing variant.

    Explicit approval can add differing content only to a missing variant of a
    single matching title. Existing variants and ambiguous versions are never replaced.
    """
    variant = Variant(**dict(draft.variant), source=source)
    if not versions:
        return MergeResult(
            MergeOutcome.CREATED,
            Recipe(
                id=recipe_id_for(draft.title),
                title=draft.title,
                steps=draft.steps,
                notes=draft.notes,
                meal_types=list(dict.fromkeys(draft.meal_types)),
                dish_types=list(dict.fromkeys(draft.dish_types)),
                suggested_batch_portions=draft.suggested_batch_portions,
                variants={kind: variant},
            ),
        )
    fingerprint = draft_fingerprint(draft)
    for recipe in versions:
        current = recipe.variants.get(kind)
        if (
            current
            and content_fingerprint(recipe.title, current, recipe.steps_for(kind)) == fingerprint
        ):
            return MergeResult(MergeOutcome.UNCHANGED, recipe)

    incoming_names = {
        ingredient.name.casefold().strip() for ingredient in draft.variant.ingredients
    }
    candidates = [
        recipe
        for recipe in versions
        if kind not in recipe.variants
        and any(
            incoming_names == {ingredient.name.casefold().strip() for ingredient in v.ingredients}
            and [" ".join(step.split()) for step in recipe.steps_for(k)]
            == [" ".join(step.split()) for step in draft.steps]
            for k, v in recipe.variants.items()
        )
    ]
    if allow_variant_differences and len(versions) == 1 and kind not in versions[0].variants:
        candidates = [versions[0]]
    if len(candidates) != 1:
        return MergeResult(
            MergeOutcome.CONFLICT,
            versions[0],
            "Existing title has different content or an ambiguous version; review required.",
        )
    target = candidates[0]
    variant = variant.model_copy(
        update={"steps": None if draft.steps == target.steps else draft.steps}
    )
    return MergeResult(
        MergeOutcome.VARIANT_ADDED,
        target.model_copy(update={"variants": {**target.variants, kind: variant}}),
    )
