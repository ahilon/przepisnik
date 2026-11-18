"""Write small independent PDF fixtures without requiring external fonts or PDF engines."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING
from zlib import compress

from PIL import Image

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

_PAGE_HEIGHT = 842
_PAGE_WIDTH = 595
_TEXT_LEFT = 40
_TEXT_TOP = 40
_LINE_HEIGHT = 18
_CMAP_CHUNK_SIZE = 100


class PdfFixtureWriter:
    """Build PDF objects and cross references independently of the reader under test."""

    def __init__(self) -> None:
        """Reserve the document catalog and page tree before adding content."""
        self._objects: list[bytes] = [b"", b""]

    def write(self, path: Path, pages: Sequence[Sequence[str]], image: bytes | None) -> Path:
        """Write mapped Unicode text and an optional image on each page.

        Args:
            path: Destination inside a disposable test directory.
            pages: Ordered text lines for each page.
            image: Optional encoded image placed at top=30 on each page.

        Returns:
            Path: The generated PDF, with explicit Unicode mappings and xref offsets.
        """
        characters = sorted({character for lines in pages for text in lines for character in text})
        codes = {character: index for index, character in enumerate(characters, start=1)}
        font = self._font(codes)
        picture = self._image(image) if image is not None else None
        page_refs: list[int] = []
        for lines in pages:
            operations = [
                f"BT /F0 10 Tf 1 0 0 1 {_TEXT_LEFT} "
                f"{_PAGE_HEIGHT - _TEXT_TOP - row * _LINE_HEIGHT} "
                f"Tm <{''.join(f'{codes[character]:04x}' for character in text)}> Tj ET"
                for row, text in enumerate(lines)
            ]
            image_resource = ""
            if picture is not None:
                operations.append(f"q 40 0 0 40 400 {_PAGE_HEIGHT - 70} cm /Im0 Do Q")
                image_resource = f"/XObject << /Im0 {picture} 0 R >>"
            content = self._stream("", "\n".join(operations).encode("ascii"))
            page_refs.append(
                self._add(
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
                    f"/Resources << /Font << /F0 {font} 0 R >> {image_resource} >> "
                    f"/Contents {content} 0 R >>".encode("ascii")
                )
            )
        self._objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        children = " ".join(f"{reference} 0 R" for reference in page_refs)
        self._objects[1] = f"<< /Type /Pages /Count {len(page_refs)} /Kids [{children}] >>".encode(
            "ascii"
        )
        path.write_bytes(self._serialize())
        return path

    def _add(self, content: bytes) -> int:
        """Append one indirect object and return its 1-based object number."""
        self._objects.append(content)
        return len(self._objects)

    def _stream(self, attributes: str, content: bytes) -> int:
        """Store an explicit-length binary stream with the supplied PDF attributes."""
        header = f"<< {attributes} /Length {len(content)} >>\nstream\n".encode("ascii")
        return self._add(header + content + b"\nendstream")

    def _font(self, codes: dict[str, int]) -> int:
        """Build a Unicode-mapped nonembedded CID font for extraction-only fixtures."""
        mappings = [
            f"<{code:04x}> <{character.encode('utf-16-be').hex()}>"
            for character, code in codes.items()
        ]
        chunks = [
            f"{len(mappings[start : start + _CMAP_CHUNK_SIZE])} beginbfchar\n"
            + "\n".join(mappings[start : start + _CMAP_CHUNK_SIZE])
            + "\nendbfchar"
            for start in range(0, len(mappings), _CMAP_CHUNK_SIZE)
        ]
        cmap = (
            "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /DemoUnicode def\n/CMapType 2 def\n"
            "1 begincodespacerange\n<0000> <ffff>\nendcodespacerange\n"
            + "\n".join(chunks)
            + "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
        )
        mapping = self._stream("", cmap.encode("ascii"))
        descriptor = self._add(
            b"<< /Type /FontDescriptor /FontName /DemoSans /Flags 32 "
            b"/FontBBox [0 -200 1000 1000] /ItalicAngle 0 /Ascent 800 /Descent -200 "
            b"/CapHeight 700 /StemV 80 >>"
        )
        descendant = self._add(
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /DemoSans "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {descriptor} 0 R /DW 600 /CIDToGIDMap /Identity >>".encode("ascii")
        )
        return self._add(
            f"<< /Type /Font /Subtype /Type0 /BaseFont /DemoSans /Encoding /Identity-H "
            f"/DescendantFonts [{descendant} 0 R] /ToUnicode {mapping} 0 R >>".encode("ascii")
        )

    def _image(self, content: bytes) -> int:
        """Embed JPEG bytes unchanged, or RGB samples plus a separate alpha soft mask."""
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            dimensions = f"/Type /XObject /Subtype /Image /Width {width} /Height {height}"
            if image.format == "JPEG":
                return self._stream(
                    f"{dimensions} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode",
                    content,
                )
            mask_resource = ""
            if "A" in image.getbands():
                with image.getchannel("A") as alpha:
                    mask = self._stream(
                        f"{dimensions} /ColorSpace /DeviceGray /BitsPerComponent 8 "
                        "/Filter /FlateDecode",
                        compress(alpha.tobytes()),
                    )
                mask_resource = f"/SMask {mask} 0 R"
            with image.convert("RGB") as rgb:
                return self._stream(
                    f"{dimensions} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
                    f"/Filter /FlateDecode {mask_resource}",
                    compress(rgb.tobytes()),
                )

    def _serialize(self) -> bytes:
        """Write a complete PDF with offsets calculated from bytes, not text length."""
        with BytesIO() as output:
            output.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
            offsets = [0]
            for number, obj in enumerate(self._objects, start=1):
                offsets.append(output.tell())
                output.write(f"{number} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
            xref = output.tell()
            output.write(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
            for offset in offsets[1:]:
                output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
            output.write(
                f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n".encode("ascii")
            )
            return output.getvalue()
