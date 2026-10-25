"""Conservative meal classification from explicit labels and source time ranges."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from przepisnik.core.models import MealType, slugify

TIME_RANGE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})\s*[-\u2013\u2014]\s*(\d{1,2}):(\d{2})(?!\d)")
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MEAL_WINDOWS = (
    (6 * MINUTES_PER_HOUR, 10 * MINUTES_PER_HOUR, MealType.BREAKFAST),
    (12 * MINUTES_PER_HOUR, 16 * MINUTES_PER_HOUR, MealType.LUNCH),
    (17 * MINUTES_PER_HOUR, 22 * MINUTES_PER_HOUR, MealType.DINNER),
)


@dataclass(frozen=True, slots=True)
class MealClassification:
    """Classification and its evidence; time-based mappings are suggestions."""

    meal_type: MealType | None = None
    basis: Literal["explicit", "time_range"] | None = None


def classify_meal(label: str) -> MealClassification:
    """Prefer Polish names; infer only ranges inside one meal window.

    Sequence numbers never imply an occasion. Ambiguous ranges remain unclassified.
    """
    words = slugify(label).split("-")
    explicit = set()
    if any(word in words for word in ("przekaska", "przekaski", "podwieczorek")):
        explicit.add(MealType.SNACK)
    if "sniadanie" in words:
        explicit.add(MealType.SNACK if "drugie" in words or "ii" in words else MealType.BREAKFAST)
    if "obiad" in words:
        explicit.add(MealType.LUNCH)
    if "kolacja" in words:
        explicit.add(MealType.DINNER)
    if len(explicit) == 1:
        return MealClassification(explicit.pop(), "explicit")
    if explicit:
        return MealClassification()
    match = TIME_RANGE.search(label)
    if match is None:
        return MealClassification()
    start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
    if not (
        0 <= start_hour < HOURS_PER_DAY
        and 0 <= end_hour < HOURS_PER_DAY
        and 0 <= start_minute < MINUTES_PER_HOUR
        and 0 <= end_minute < MINUTES_PER_HOUR
    ):
        return MealClassification()
    start = start_hour * MINUTES_PER_HOUR + start_minute
    end = end_hour * MINUTES_PER_HOUR + end_minute
    for lower, upper, kind in MEAL_WINDOWS:
        if lower <= start <= end <= upper:
            return MealClassification(kind, "time_range")
    return MealClassification()
