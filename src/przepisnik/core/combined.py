"""Derive a shared meal without modifying either stored portion variant."""

from math import isfinite
from typing import Final

from przepisnik.core.models import Ingredient, Nutrition, Recipe, Variant, VariantKind

COMBINED_VARIANT: Final = "combined"
COMBINED_SERVINGS: Final = 2
UNIT_CONVERSIONS: Final = {
    "kg": ("g", 1000.0),
    "l": ("ml", 1000.0),
    "szt": ("szt.", 1.0),
    "sztuki": ("szt.", 1.0),
}
type Quantity = tuple[float, str]
type OptionalQuantity = tuple[float | None, str | None]
type IngredientKey = tuple[str, str]


class CombinedVariantBuilder:
    """Combine one female and one male serving only when their recipes agree."""

    def build(self, recipe: Recipe) -> Variant | None:
        """Derive two servings with shared products and identical ordered steps.

        Args:
            recipe: Stored recipe whose original variants remain untouched.

        Returns:
            Variant | None: A display-only variant, or None for missing,
                incompatible or ambiguous source data.
        """
        female = recipe.variants.get(VariantKind.FEMALE)
        male = recipe.variants.get(VariantKind.MALE)
        if female is None or male is None:
            return None
        female_steps = recipe.steps_for(VariantKind.FEMALE)
        male_steps = recipe.steps_for(VariantKind.MALE)
        if [self._text(step) for step in female_steps] != [self._text(step) for step in male_steps]:
            return None
        female_products = self._index(female.ingredients)
        male_products = self._index(male.ingredients)
        if female_products is None or male_products is None:
            return None
        if female_products.keys() != male_products.keys():
            return None
        servings = (female.servings, male.servings)
        ingredients: list[Ingredient] = []
        for key, ingredient in female_products.items():
            combined = self._ingredient(ingredient, male_products[key], servings)
            if combined is None:
                return None
            ingredients.append(combined)
        return Variant(
            servings=COMBINED_SERVINGS,
            ingredients=ingredients,
            steps=female_steps.copy(),
            nutrition=self._nutrition(female, male),
        )

    @staticmethod
    def _text(value: str) -> str:
        """Normalize cosmetic whitespace and case for exact text comparisons.

        Args:
            value: Product, group or preparation text.

        Returns:
            str: Case-insensitive text with collapsed whitespace.
        """
        return " ".join(value.split()).casefold()

    def _index(self, ingredients: list[Ingredient]) -> dict[IngredientKey, Ingredient] | None:
        """Match products independently of order while retaining preparation groups.

        Args:
            ingredients: One variant's source ingredient rows.

        Returns:
            dict | None: Unique product/group keys, or None for ambiguous repeats.
        """
        indexed: dict[IngredientKey, Ingredient] = {}
        for ingredient in ingredients:
            key = (self._text(ingredient.name), self._text(ingredient.group or ""))
            if key in indexed:
                return None
            indexed[key] = ingredient
        return indexed

    def _ingredient(
        self, left: Ingredient, right: Ingredient, servings: tuple[int, int]
    ) -> Ingredient | None:
        """Sum compatible complete quantities, never treating unknown amounts as zero.

        Args:
            left: Female ingredient row.
            right: Matching male ingredient row.
            servings: Original female and male serving counts.

        Returns:
            Ingredient | None: Summed row or None when no safe quantity exists.
        """
        household = self._quantity((left.amount, left.unit), (right.amount, right.unit), servings)
        metric = None
        if left.metric_amount is not None or right.metric_amount is not None:
            left_metric = (
                (left.metric_amount, left.metric_unit)
                if left.metric_amount is not None
                else (left.amount, left.unit)
            )
            right_metric = (
                (right.metric_amount, right.metric_unit)
                if right.metric_amount is not None
                else (right.amount, right.unit)
            )
            metric = self._quantity(left_metric, right_metric, servings)
        if left.metric_amount is not None and right.metric_amount is not None and metric is None:
            return None
        if household is None and metric is None:
            if any(
                value is not None
                for value in (left.amount, right.amount, left.metric_amount, right.metric_amount)
            ):
                return None
            if self._text(left.raw or "") != self._text(right.raw or ""):
                return None
            if self._text(left.unit or "") != self._text(right.unit or ""):
                return None
            return left.model_copy(deep=True)
        return Ingredient(
            name=left.name,
            group=left.group,
            amount=household[0] if household else None,
            unit=household[1] if household else None,
            metric_amount=metric[0] if metric else None,
            metric_unit=("g" if metric[1] == "g" else "ml") if metric else None,
        )

    def _quantity(
        self, left: OptionalQuantity, right: OptionalQuantity, servings: tuple[int, int]
    ) -> Quantity | None:
        """Convert compatible units and sum one serving of each source quantity.

        Args:
            left: Female amount and unit, possibly unspecified.
            right: Male amount and unit, possibly unspecified.
            servings: Source serving counts used before summation.

        Returns:
            tuple | None: Finite total and normalized unit, or None if incompatible.
        """
        if left[0] is None or right[0] is None:
            return None
        left_unit = self._text(left[1] or "")
        right_unit = self._text(right[1] or "")
        left_unit, left_factor = UNIT_CONVERSIONS.get(left_unit, (left_unit, 1.0))
        right_unit, right_factor = UNIT_CONVERSIONS.get(right_unit, (right_unit, 1.0))
        if left_unit != right_unit:
            return None
        left_amount = left[0] / servings[0] * left_factor
        right_amount = right[0] / servings[1] * right_factor
        total = left_amount + right_amount
        return (total, left_unit) if isfinite(total) else None

    def _nutrition(self, female: Variant, male: Variant) -> Nutrition | None:
        """Include nutrition only when both source servings have complete finite data.

        Args:
            female: Original female variant.
            male: Original male variant.

        Returns:
            Nutrition | None: Per-person totals for the pair, or unknown nutrition.
        """
        if female.nutrition is None or male.nutrition is None:
            return None
        female_values = female.nutrition.model_dump()
        male_values = male.nutrition.model_dump()
        totals = {
            key: female_values[key] / female.servings + male_values[key] / male.servings
            for key in female_values
        }
        return Nutrition(**totals) if all(isfinite(value) for value in totals.values()) else None
