"""Check parser lookup by name and automatic source detection."""

from pathlib import Path

import pytest

from przepisnik.errors import UnsupportedSourceError
from przepisnik.parsers.base import ParseResult, RecipeParser
from przepisnik.parsers.registry import ParserRegistry, default_registry


class SuffixParser(RecipeParser):
    """Parser accepting files with one suffix."""

    def __init__(self, name: str, suffix: str) -> None:
        """Remember the parser name and accepted suffix."""
        self._name = name
        self._suffix = suffix

    @property
    def name(self) -> str:
        """Return the configured name."""
        return self._name

    def can_parse(self, source: Path) -> bool:
        """Accept files with the configured suffix."""
        return source.suffix == self._suffix

    def parse(self, source: Path) -> ParseResult:
        """Return no recipes."""
        return ParseResult(recipes=[], warnings=[str(source)])


@pytest.fixture
def registry() -> ParserRegistry:
    """Return a registry where two parsers accept PDFs."""
    return ParserRegistry(
        [SuffixParser("html", ".html"), SuffixParser("first", ".pdf"), SuffixParser("next", ".pdf")]
    )


def test_registry_lists_and_returns_parsers_by_name(registry: ParserRegistry) -> None:
    """Keep registration order and look parsers up by name."""
    assert registry.names == ["html", "first", "next"]
    assert registry.get("next").name == "next"


def test_unknown_parser_name_lists_available_parsers(registry: ParserRegistry) -> None:
    """Explain which parser names exist."""
    with pytest.raises(UnsupportedSourceError, match="available: html, first, next"):
        registry.get("docx")


def test_detection_uses_first_matching_parser(registry: ParserRegistry) -> None:
    """Prefer the earliest registered parser accepting the source."""
    assert registry.detect(Path("plan.pdf")).name == "first"
    assert registry.detect(Path("page.html")).parse(Path("page.html")).warnings == ["page.html"]


def test_unrecognised_source_points_to_agent_workflow(registry: ParserRegistry) -> None:
    """Suggest the agent workflow for sources without a parser."""
    with pytest.raises(UnsupportedSourceError, match="agent workflow"):
        registry.detect(Path("photo.jpg"))


def test_default_registry_contains_respo() -> None:
    """Register the built-in Respo parser."""
    assert default_registry().names == ["respo"]
