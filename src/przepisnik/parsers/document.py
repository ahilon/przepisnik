"""Source-agnostic document primitives consumed by recipe parsers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from przepisnik.core.models import ImageData


@dataclass(frozen=True, slots=True)
class TextLine:
    """Single line of text with its position in the document."""

    text: str
    page: int
    top: float


@dataclass(frozen=True, slots=True)
class ImageRef:
    """Placement of an embedded image on a page."""

    xref: int
    page: int
    top: float
    width: int
    height: int


class Document(Protocol):
    """Read-only view of a paged document (1-based page numbers)."""

    def lines(self) -> list[TextLine]:
        """Return all non-empty text lines in reading order."""
        ...

    def images(self) -> list[ImageRef]:
        """Return all embedded image placements."""
        ...

    def extract_image(self, ref: ImageRef) -> ImageData:
        """Return the original file content of an embedded image."""
        ...
