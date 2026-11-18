"""Read text lines and images from generated PDF files."""

from contextlib import closing
from io import BytesIO
from pathlib import Path

import pytest
from factories import PNG_BYTES, RESPO_LINES, write_pdf
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from przepisnik.adapters.pdf import PdfDocument
from przepisnik.errors import SourceReadError
from przepisnik.parsers.document import ImageRef


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
    with Image.new("RGBA", (4, 4), (200, 100, 50, 80)) as source, BytesIO() as output:
        source.save(output, format="PNG")
        path = write_pdf(tmp_path / "plan.pdf", [["Tekst"]], image=output.getvalue())
    with PdfDocument(path) as document:
        [ref] = document.images()
        image = document.extract_image(ref)
    assert image.extension == "png"
    with Image.open(BytesIO(image.content)) as decoded:
        assert decoded.mode == "RGBA"
        assert decoded.getpixel((0, 0)) == (200, 100, 50, 80)


def test_jpeg_extension_is_normalised(tmp_path: Path) -> None:
    """Store JPEG images with the common jpg extension."""
    with Image.new("RGB", (4, 4), (200, 200, 200)) as source, BytesIO() as output:
        source.save(output, format="JPEG")
        original = output.getvalue()
        path = write_pdf(tmp_path / "plan.pdf", [["Tekst"]], image=original)
    with PdfDocument(path) as document:
        [ref] = document.images()
        image = document.extract_image(ref)
        assert image.extension == "jpg"
        assert image.content == original


def test_missing_or_invalid_files_raise_source_errors(tmp_path: Path) -> None:
    """Report unreadable sources as expected errors."""
    with pytest.raises(SourceReadError):
        PdfDocument(tmp_path / "missing.pdf")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    with pytest.raises(SourceReadError):
        PdfDocument(broken)


def test_repeated_image_placements_keep_their_page_positions(tmp_path: Path) -> None:
    """Find both painted uses of one image rather than deduplicating its PDF object."""
    source = write_pdf(tmp_path / "source.pdf", [["Tekst"]], image=PNG_BYTES)
    path = tmp_path / "repeated.pdf"
    with closing(PdfWriter(clone_from=source)) as writer:
        page = writer.pages[0]
        contents = page.get_contents()
        assert contents is not None
        stream = DecodedStreamObject()
        stream.set_data(contents.get_data() + b"\nq 40 0 0 40 400 672 cm /Im0 Do Q")
        page.replace_contents(ContentStream(stream, writer))
        writer.write(path)
    with PdfDocument(path) as document:
        first, second = document.images()
        assert first.xref == second.xref
        assert [first.top, second.top] == pytest.approx([30, 130])
        assert document.extract_image(first) == document.extract_image(second)


def test_form_matrix_and_outer_translation_apply_to_text_and_images(tmp_path: Path) -> None:
    """Keep nested form text and photos aligned in the enclosing page's coordinates."""
    source = write_pdf(tmp_path / "source.pdf", [["Łyżka – 1", "Druga"]], image=PNG_BYTES)
    path = tmp_path / "form.pdf"
    with closing(PdfWriter(clone_from=source)) as writer:
        page = writer.pages[0]
        contents = page.get_contents()
        assert contents is not None
        form = DecodedStreamObject()
        form.set_data(contents.get_data())
        form.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): page.mediabox,
                NameObject("/Resources"): page["/Resources"],
                NameObject("/Matrix"): ArrayObject([NumberObject(n) for n in (1, 0, 0, 1, 0, -20)]),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/XObject"): DictionaryObject(
                    {NameObject("/Wrapped"): writer._add_object(form)}
                ),
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(b"q 1 0 0 1 0 -30 cm /Wrapped Do Q")
        page.replace_contents(ContentStream(stream, writer))
        writer.write(path)
    with PdfDocument(path) as document:
        lines = document.lines()
        assert [line.text for line in lines] == ["Łyżka – 1", "Druga"]
        assert [line.top for line in lines] == pytest.approx([90, 108])
        [image] = document.images()
        assert image.top == pytest.approx(80)
        assert document.extract_image(image).content.startswith(b"\x89PNG")


def test_text_leading_preserves_positions_inside_one_text_object(tmp_path: Path) -> None:
    """Use explicit PDF line spacing when one text callback contains several lines."""
    source = write_pdf(tmp_path / "source.pdf", [["Pierwsza", "Druga"]])
    path = tmp_path / "leading.pdf"
    with closing(PdfWriter(clone_from=source)) as writer:
        page = writer.pages[0]
        contents = page.get_contents()
        assert contents is not None
        rows = contents.get_data().splitlines()
        strings = [row.split(b"<")[1].split(b">")[0] for row in rows]
        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F0 10 Tf 18 TL 1 0 0 1 40 802 Tm <"
            + strings[0]
            + b"> Tj T* <"
            + strings[1]
            + b"> Tj ET"
        )
        page.replace_contents(ContentStream(stream, writer))
        writer.write(path)
    with PdfDocument(path) as document:
        lines = document.lines()
        assert [line.text for line in lines] == ["Pierwsza", "Druga"]
        assert [line.top for line in lines] == pytest.approx([40, 58])


def test_password_protected_pdf_is_reported_as_a_source_error(tmp_path: Path) -> None:
    """Reject protected input without leaking a backend exception to the CLI."""
    path = tmp_path / "protected.pdf"
    with PdfWriter() as writer:
        writer.add_blank_page(width=595, height=842)
        writer.encrypt("synthetic-fixture-only")
        writer.write(path)
    with pytest.raises(SourceReadError, match="password"):
        PdfDocument(path)


def test_blank_pages_are_valid_and_closed_documents_cannot_be_reused(tmp_path: Path) -> None:
    """Allow an empty page and release the reader even when results were cached."""
    path = write_pdf(tmp_path / "blank.pdf", [[]])
    document = PdfDocument(path)
    assert document.lines() == []
    assert document.images() == []
    document.close()
    document.close()
    with pytest.raises(SourceReadError, match="closed"):
        document.lines()


def test_unknown_image_reference_is_reported_as_a_source_error(tmp_path: Path) -> None:
    """Reject an image reference that was not obtained from this document."""
    path = write_pdf(tmp_path / "plan.pdf", [["Tekst"]])
    with PdfDocument(path) as document, pytest.raises(SourceReadError, match="extract image"):
        document.extract_image(ImageRef(xref=999, page=1, top=0, width=1, height=1))


def test_rotation_keeps_reading_source_unchanged(tmp_path: Path) -> None:
    """Transform both kinds of coordinates without writing or normalizing the source."""
    source = write_pdf(tmp_path / "source.pdf", [["Tekst"]], image=PNG_BYTES)
    path = tmp_path / "rotated.pdf"
    with closing(PdfWriter(clone_from=source)) as writer:
        writer.pages[0].rotate(90)
        writer.write(path)
    original = path.read_bytes()
    with PdfDocument(path) as document:
        [line] = document.lines()
        [image] = document.images()
        assert line.text == "Tekst"
        assert line.top == pytest.approx(40)
        assert image.top == pytest.approx(400)
        assert document.extract_image(image).content.startswith(b"\x89PNG")
    assert path.read_bytes() == original


def test_unused_image_resource_is_not_assigned_to_a_recipe(tmp_path: Path) -> None:
    """Ignore an image resource that is never actually drawn on the page."""
    source = write_pdf(tmp_path / "source.pdf", [["Tekst"]], image=PNG_BYTES)
    path = tmp_path / "unused.pdf"
    with closing(PdfWriter(clone_from=source)) as writer:
        page = writer.pages[0]
        contents = page.get_contents()
        assert contents is not None
        stream = DecodedStreamObject()
        stream.set_data(contents.get_data().replace(b"/Im0 Do", b""))
        page.replace_contents(ContentStream(stream, writer))
        writer.write(path)
    with PdfDocument(path) as document:
        assert [line.text for line in document.lines()] == ["Tekst"]
        assert document.images() == []


@pytest.mark.parametrize(
    ("spans", "expected"),
    [
        ([("Posiłek 1 /", 40), ("7:00-10:00", 104)], ["Posiłek 1 / 7:00-10:00"]),
        ([("1", 40), (".", 46), ("Wymieszaj składniki.", 55)], ["1. Wymieszaj składniki."]),
        ([("Przygo", 40), ("towanie", 76)], ["Przygotowanie"]),
        ([("719", 40), ("Kcal", 350)], ["719", "Kcal"]),
    ],
)
def test_positioned_spans_form_lines_without_merging_columns(
    tmp_path: Path, spans: list[tuple[str, int]], expected: list[str]
) -> None:
    """Reassemble independent text objects by geometry, ignoring synthetic newlines.

    Args:
        tmp_path: Disposable generated PDF directory.
        spans: Synthetic text and its horizontal position on one baseline.
        expected: Physical lines, including a separate distant column.

    Returns:
        None: Styled headers, steps and words remain readable without merging columns.
    """
    source = write_pdf(tmp_path / "source.pdf", [[text for text, _ in spans]])
    path = tmp_path / "positioned.pdf"
    with closing(PdfWriter(clone_from=source)) as writer:
        page = writer.pages[0]
        contents = page.get_contents()
        assert contents is not None
        strings = [row.split(b"<")[1].split(b">")[0] for row in contents.get_data().splitlines()]
        resources = page["/Resources"]
        assert isinstance(resources, DictionaryObject)
        fonts = resources["/Font"]
        assert isinstance(fonts, DictionaryObject)
        original_font = fonts["/F0"]
        assert isinstance(original_font, DictionaryObject)
        fonts[NameObject("/F1")] = writer._add_object(DictionaryObject(original_font))
        stream = DecodedStreamObject()
        operations = [
            f"BT /F{index % 2} 10 Tf 1 0 0 1 {x} 802 Tm <".encode("ascii") + text + b"> Tj ET"
            for index, ((_, x), text) in enumerate(zip(spans, strings, strict=True))
        ]
        stream.set_data(b"\n".join(operations))
        page.replace_contents(ContentStream(stream, writer))
        writer.write(path)
    with PdfDocument(path) as document:
        assert [line.text for line in document.lines()] == expected
