"""Check conservative meal classification from labels and time ranges."""

import pytest

from przepisnik.core.meals import MealClassification, classify_meal
from przepisnik.core.models import MealType


@pytest.mark.parametrize(
    ("label", "meal_type"),
    [
        ("Śniadanie", MealType.BREAKFAST),
        ("II śniadanie", MealType.SNACK),
        ("Drugie śniadanie 10:00-11:00", MealType.SNACK),
        ("Obiad 07:00-08:00", MealType.LUNCH),
        ("Kolacja", MealType.DINNER),
        ("Podwieczorek", MealType.SNACK),
        ("Przekąska", MealType.SNACK),
    ],
)
def test_explicit_names_win_over_time_ranges(label: str, meal_type: MealType) -> None:
    """Classify Polish meal names even when the time range suggests otherwise."""
    assert classify_meal(label) == MealClassification(meal_type, "explicit")


@pytest.mark.parametrize(
    ("label", "meal_type"),
    [
        ("Posiłek 1 / 07:00-09:30", MealType.BREAKFAST),
        ("Posiłek 2 / 12:00–15:00", MealType.LUNCH),
        ("18:00 — 21:00", MealType.DINNER),
        ("6:00-10:00", MealType.BREAKFAST),
    ],
)
def test_ranges_inside_one_window_are_suggestions(label: str, meal_type: MealType) -> None:
    """Infer the meal from a range that fits entirely in one meal window."""
    assert classify_meal(label) == MealClassification(meal_type, "time_range")


@pytest.mark.parametrize(
    "label",
    [
        "Obiad lub kolacja",
        "Posiłek 3",
        "Posiłek 2 / 09:00-13:00",
        "10:30-11:30",
        "25:00-26:00",
        "10:75-11:00",
        "12:00-112:00",
        "",
    ],
)
def test_ambiguous_or_invalid_labels_stay_unclassified(label: str) -> None:
    """Never guess: conflicting names, gaps between windows and invalid times."""
    assert classify_meal(label) == MealClassification()
