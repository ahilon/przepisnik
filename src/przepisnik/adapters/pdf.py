"""PDF adapter implementing :class:`przepisnik.parsers.document.Document` with PyMuPDF."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

import pymupdf

from przepisnik.core.models import ImageData
from przepisnik.errors import SourceReadError
from przepisnik.parsers.document import ImageRef, TextLine

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType

_EXTENSION_ALIASES = {"jpeg": "jpg"}


class PdfDocument:
    """Text lines and embedded images of a PDF file."""

    def __init__(self, path: Path) -> None:
        """Open the PDF file.

        Args:
            path: Path to the PDF file.

        Raises:
            SourceReadError: If the file is missing or is not a readable PDF.
        """
        try:
            # PyMuPDF ships incomplete type hints; the handle is treated as dynamic.
            self._doc: Any = pymupdf.open(path)
        except (RuntimeError, OSError) as exc:
            raise SourceReadError(f"Cannot open PDF {path}: {exc}") from exc

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying PDF handle."""
        self._doc.close()

    def lines(self) -> list[TextLine]:
        """Return all non-empty text lines in the order stored in the PDF."""
        result: list[TextLine] = []
        for page in self._doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(span["text"] for span in line["spans"]).strip()
                    if text:
                        result.append(TextLine(text, page.number + 1, float(line["bbox"][1])))
        return result

    def images(self) -> list[ImageRef]:
        """Return every placement of every embedded image."""
        result: list[ImageRef] = []
        for page in self._doc:
            for image in page.get_images(full=True):
                xref, width, height = image[0], image[2], image[3]
                result.extend(
                    ImageRef(xref, page.number + 1, float(rect.y0), width, height)
                    for rect in page.get_image_rects(xref)
                )
        return result

    def extract_image(self, ref: ImageRef) -> ImageData:
        """Return an embedded image; images with a transparency mask become PNG.

        Without applying the soft mask, transparent areas (e.g. around a plate)
        would come out black.
        """
        info = self._doc.extract_image(ref.xref)
        mask_xref = int(info.get("smask") or 0)
        if mask_xref:
            base = pymupdf.Pixmap(self._doc, ref.xref)
            mask = pymupdf.Pixmap(self._doc, mask_xref)
            return ImageData(pymupdf.Pixmap(base, mask).tobytes("png"), "png")
        extension = str(info["ext"]).lower()
        return ImageData(bytes(info["image"]), _EXTENSION_ALIASES.get(extension, extension))
