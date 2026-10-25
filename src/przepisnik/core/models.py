"""Recipe data model - the common denominator of every source and the template contract."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, PositiveInt

SCHEMA_VERSION: Final = 1
RECIPE_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
AGENT_PARSER = "agent"


class VariantKind(StrEnum):
    """Audience a recipe variant (portion size) is prepared for."""

    MALE = "male"
    FEMALE = "female"
    FAMILY = "family"

    @property
    def label(self) -> str:
        """Return the Polish display label used in templates and conversation."""
        return VARIANT_LABELS[self]


VARIANT_LABELS: dict[VariantKind, str] = {
    VariantKind.MALE: "Mężczyzna",
    VariantKind.FEMALE: "Kobieta",
    VariantKind.FAMILY: "Rodzina",
}


@dataclass(frozen=True, slots=True)
class ImageData:
    """Raw image file content."""

    content: bytes
    extension: str


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Nutrition(_Model):
    """Macronutrients for the whole variant (all of its servings)."""

    kcal: NonNegativeFloat
    protein_g: NonNegativeFloat
    fat_g: NonNegativeFloat
    carbs_g: NonNegativeFloat


class Ingredient(_Model):
    """Single ingredient line, parsed into household and metric quantities."""

    name: str = Field(min_length=1)
    amount: float | None = Field(default=None, description="Household amount, e.g. 1.5.")
    unit: str | None = Field(default=None, description="Household unit, e.g. 'łyżki'.")
    metric_amount: float | None = Field(default=None, description="Weight or volume.")
    metric_unit: Literal["g", "ml"] | None = None
    group: str | None = Field(default=None, description="Sub-list name, e.g. 'Do podania'.")
    raw: str | None = Field(default=None, description="Original ingredient text.")


class Source(_Model):
    """Where a variant was extracted from."""

    parser: str = Field(description="Parser name, or 'agent' for agent-written drafts.")
    file: str | None = None
    url: str | None = None
    sha256: str | None = None
    page: int | None = None


class VariantData(_Model):
    """Portion-dependent part of a recipe, as delivered by a source."""

    servings: PositiveInt = Field(
        default=1, description="Number of servings that nutrition and ingredients describe."
    )
    nutrition: Nutrition | None = Field(
        default=None, description="Only values stated by the source; never estimated."
    )
    ingredients: list[Ingredient] = Field(min_length=1)


class Variant(VariantData):
    """Stored recipe variant with its provenance."""

    steps: list[str] | None = Field(
        default=None, description="Variant-specific steps; None means the recipe steps apply."
    )
    source: Source | None = None


class RecipeDraft(_Model):
    """Recipe extracted from one source, before it is merged into the store."""

    title: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)
    suggested_batch_portions: int | None = Field(
        default=None,
        ge=2,
        description="Suggested number of portions to cook at once; data stays per serving.",
    )
    variant: VariantData


class DraftItem(RecipeDraft):
    """Entry of a draft file written by an agent for sources without a parser."""

    image_file: str | None = Field(
        default=None, description="Path to the dish photo, relative to the draft file."
    )
    page: int | None = Field(default=None, description="Page of the source document.")


class Recipe(_Model):
    """Stored recipe with all of its variants."""

    schema_version: Literal[1] = SCHEMA_VERSION
    id: str = Field(pattern=RECIPE_ID_PATTERN)
    title: str = Field(min_length=1)
    version: PositiveInt = Field(
        default=1, description="Distinguishes different recipes sharing the same title."
    )
    image: str | None = Field(default=None, description="Image file name in the recipe folder.")
    steps: list[str] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)
    suggested_batch_portions: int | None = Field(default=None, ge=2)
    variants: dict[VariantKind, Variant]

    def steps_for(self, kind: VariantKind) -> list[str]:
        """Return the steps to show for a variant (its own, or the recipe steps)."""
        variant = self.variants.get(kind)
        return variant.steps if variant is not None and variant.steps else self.steps


class ImportedSource(_Model):
    """Registry entry of an imported source."""

    key: str = Field(description="Content hash of the source file, or its URL.")
    name: str
    parser: str
    variant: VariantKind
    imported_at: datetime
    recipe_count: int


def slugify(text: str) -> str:
    """Build an ASCII-only, lowercase, hyphen-separated slug.

    Args:
        text: Any text, possibly with Polish diacritics.

    Returns:
        Slug, e.g. ``"zupa-krem-z-dyni"`` for ``"Zupa krem z dyni"``.
    """
    ascii_text = (
        unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def recipe_id_for(title: str, version: int = 1) -> str:
    """Return the id of a recipe version: ``<slug>`` for 1, ``<slug>-<n>`` otherwise."""
    base = slugify(title)
    return base if version == 1 else f"{base}-{version}"
