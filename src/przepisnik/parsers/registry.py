"""Registry choosing the parser for a source."""

from __future__ import annotations

from typing import TYPE_CHECKING

from przepisnik.errors import UnsupportedSourceError
from przepisnik.parsers.respo import RespoParser

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from przepisnik.parsers.base import RecipeParser

AGENT_HINT = "extract recipes with the agent workflow ('schema' + 'add')"


class ParserRegistry:
    """Ordered collection of parsers; the first one accepting a source wins."""

    def __init__(self, parsers: Sequence[RecipeParser]) -> None:
        """Create a registry from parsers in detection order."""
        self._parsers = {parser.name: parser for parser in parsers}

    @property
    def names(self) -> list[str]:
        """Return the names of all registered parsers."""
        return list(self._parsers)

    def get(self, name: str) -> RecipeParser:
        """Return a parser by name.

        Raises:
            UnsupportedSourceError: If no parser has this name.
        """
        try:
            return self._parsers[name]
        except KeyError:
            raise UnsupportedSourceError(
                f"Unknown parser '{name}'; available: {', '.join(self.names)}."
            ) from None

    def detect(self, source: Path) -> RecipeParser:
        """Return the first parser that recognises the source.

        Raises:
            UnsupportedSourceError: If no parser recognises it.
        """
        for parser in self._parsers.values():
            if parser.can_parse(source):
                return parser
        raise UnsupportedSourceError(f"No parser recognises {source}; {AGENT_HINT}.")


def default_registry() -> ParserRegistry:
    """Return the registry with all built-in parsers."""
    return ParserRegistry([RespoParser()])
