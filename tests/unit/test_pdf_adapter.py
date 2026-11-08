"""Read text lines and images from generated PDF files."""

from pathlib import Path

import pymupdf
import pytest
from factories import PNG_BYTES, RESPO_LINES, write_pdf

from przepisnik.adapters.pdf import PdfDocument
from przepisnik.errors import SourceReadError


def test_lines_keep_order_page_and_position(tmp_path: Path) -> None:
    """Return non-empty lines with 1-based pages and increasing positions."""
    path = write_pdf(tmp_path / "plan.pdf", [["Pierwsza", "Druga linia"], ["Łyżka – 1"]])
    with PdfDocument(path) as document:
        lines = document.lines()
    assert [(line.text, line.page) for line in lines] == [
        ("Pierwsza", 1),
        ("Druga linia", 1),
        ("Łyżka – 1", 2),
    ]
    assert lines[0].top < lines[1].top


def test_images_are_listed_and_extracted(tmp_path: Path) -> None:
    """Locate image placements and return their original content."""
    path = write_pdf(tmp_path / "plan.pdf", [RESPO_LINES[:3]], image=PNG_BYTES)
    with PdfDocument(path) as document:
        [ref] = document.images()
        image = document.extract_image(ref)
    assert (ref.page, ref.width, ref.height) == (1, 1, 1)
    assert ref.top == pytest.approx(30)
    assert image.extension == "png"
    assert image.content.startswith(b"\x89PNG")


def test_transparent_images_are_flattened_to_png(tmp_path: Path) -> None:
    """Apply soft masks so transparent areas do not turn black."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), 1)
    pixmap.clear_with(0)
    path = write_pdf(tmp_path / "plan.pdf", [["Tekst"]], image=pixmap.tobytes("png"))
    with PdfDocument(path) as document:
        [ref] = document.images()
        image = document.extract_image(ref)
    assert image.extension == "png"
    assert pymupdf.Pixmap(image.content).alpha == 1


def test_jpeg_extension_is_normalised(tmp_path: Path) -> None:
    """Store JPEG images with the common jpg extension."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), 0)
    pixmap.clear_with(200)
    path = write_pdf(tmp_path / "plan.pdf", [["Tekst"]], image=pixmap.tobytes("jpeg"))
    with PdfDocument(path) as document:
        [ref] = document.images()
        assert document.extract_image(ref).extension == "jpg"


def test_missing_or_invalid_files_raise_source_errors(tmp_path: Path) -> None:
    """Report unreadable sources as expected errors."""
    with pytest.raises(SourceReadError):
        PdfDocument(tmp_path / "missing.pdf")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    with pytest.raises(SourceReadError):
        PdfDocument(broken)
