"""Parser contract: every source format turns its input into recipe drafts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from przepisnik.core.importer import ExtractedRecipe


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Output of a parser run."""

    recipes: list[ExtractedRecipe]
    warnings: list[str] = field(default_factory=list)


class RecipeParser(Protocol):
    """Extracts recipes from sources of one specific format."""

    @property
    def name(self) -> str:
        """Short identifier stored in each variant's source, e.g. ``"respo"``."""
        ...

    def can_parse(self, source: Path) -> bool:
        """Return True if the source looks like this parser's format."""
        ...

    def parse(self, source: Path) -> ParseResult:
        """Extract all recipes from the source."""
        ...
