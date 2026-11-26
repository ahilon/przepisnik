"""Collapse identical audience variants without scaling their stored quantities."""

import json
from collections import Counter

from przepisnik.core.models import Recipe, Variant, VariantKind

SHARED_SOURCES_STATE_PREFIX = "shared-variant-sources:"


class VariantMergeConflictError(ValueError):
    """The stored audience variants cannot be collapsed without losing differences."""


class SharedVariantMerger:
    """Compare recipe content and replace identical audiences with one shared variant."""

    def can_merge(self, recipe: Recipe) -> bool:
        """Check both audiences and any existing shared variant for identical content.

        Args:
            recipe: Stored recipe whose source records remain unchanged.

        Returns:
            bool: True when quantities, portions, nutrition and ordered steps match.
                Ingredient order and source provenance do not affect equality.
        """
        if VariantKind.FEMALE not in recipe.variants or VariantKind.MALE not in recipe.variants:
            return False
        if not self._same_content(recipe, VariantKind.FEMALE, VariantKind.MALE):
            return False
        return VariantKind.FAMILY not in recipe.variants or self._same_content(
            recipe, VariantKind.FEMALE, VariantKind.FAMILY
        )

    def merge(self, recipe: Recipe) -> Recipe:
        """Replace the matching audience pair with one unscaled shared variant.

        Args:
            recipe: Current stored recipe, revalidated by the caller before saving.

        Returns:
            Recipe: A copy with one family variant and unchanged recipe metadata.

        Raises:
            VariantMergeConflictError: If audiences are missing or content differs.
        """
        if not self.can_merge(recipe):
            raise VariantMergeConflictError("Audience variants differ or are missing")
        shared = recipe.variants.get(VariantKind.FAMILY, recipe.variants[VariantKind.FEMALE])
        source = (
            shared.source
            or recipe.variants[VariantKind.FEMALE].source
            or recipe.variants[VariantKind.MALE].source
        )
        shared = shared.model_copy(
            deep=True,
            update={
                "source": source,
                "nutrition_estimated": (
                    shared.nutrition is not None
                    and any(variant.nutrition_estimated for variant in recipe.variants.values())
                ),
            },
        )
        return recipe.model_copy(update={"variants": {VariantKind.FAMILY: shared}})

    def _same_content(self, recipe: Recipe, first: VariantKind, second: VariantKind) -> bool:
        """Compare effective steps and portion data without considering source metadata.

        Args:
            recipe: Recipe providing inherited steps and both variants.
            first: First stored audience to compare.
            second: Second stored audience to compare.

        Returns:
            bool: True when all user-facing portion content matches exactly.
        """
        left = recipe.variants[first]
        right = recipe.variants[second]
        return (
            left.servings == right.servings
            and left.nutrition == right.nutrition
            and recipe.steps_for(first) == recipe.steps_for(second)
            and self._ingredients(left) == self._ingredients(right)
        )

    @staticmethod
    def _ingredients(variant: Variant) -> Counter[str]:
        """Compare complete ingredient rows independently of their display order.

        Args:
            variant: Portion whose ingredient rows include quantities and units.

        Returns:
            Counter[str]: Stable row representations retaining duplicate-row counts.
        """
        return Counter(
            json.dumps(ingredient.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            for ingredient in variant.ingredients
        )
