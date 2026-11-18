"""Read PDF text and embedded photographs with pypdf and Pillow."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Self, cast

from PIL import Image
from pypdf import PdfReader, Transformation
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject, StreamObject
from pypdf.generic._font import Font

from przepisnik.core.models import ImageData
from przepisnik.errors import SourceReadError
from przepisnik.parsers.document import ImageRef, TextLine

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from types import TracebackType

    from pypdf import PageObject

_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_LINE_TOLERANCE = 2.0
_DEFAULT_LINE_SPACING = 1.2
_FONT_UNITS_PER_EM = 1000
_WORD_GAP_RATIO = 0.25
_MAX_WORD_GAP_SPACES = 2.0
_PDF_ERRORS = (PdfReadError, OSError, ValueError, TypeError, KeyError, NotImplementedError)


def _transform(values: Sequence[object]) -> Transformation:
    """Convert the six numeric PDF matrix values to a public pypdf transform."""
    if len(values) != len(_IDENTITY):
        raise ValueError("A PDF transformation needs six numbers")
    a, b, c, d, e, f = (float(str(value)) for value in values)
    return Transformation((a, b, c, d, e, f))


def _dictionary(parent: DictionaryObject, key: str) -> DictionaryObject:
    """Resolve a dictionary entry, accepting an absent optional resource map."""
    value = parent.get(key)
    if value is None:
        return DictionaryObject()
    resolved = value.get_object()
    if not isinstance(resolved, DictionaryObject):
        raise ValueError(f"PDF {key} must be a dictionary")
    return resolved


@dataclass
class _ContentSpace:
    """Resources and outer transformation for a page or nested Form XObject."""

    resources: DictionaryObject
    transform: Transformation
    leading: float = 0.0


@dataclass
class _Operation:
    """Track recursive visitor calls without transforming a parent's text twice."""

    space: _ContentSpace
    child: _ContentSpace | None = None
    entered: bool = False


@dataclass
class _FontWidths:
    """Decoded-character advances and word spacing in PDF font units."""

    widths: dict[str, float]
    default: float

    @classmethod
    def from_resource(cls, resource: DictionaryObject) -> Self:
        """Resolve Unicode advances through pypdf's font decoder.

        Args:
            resource: Font dictionary supplied to the text visitor.

        Returns:
            _FontWidths: Metrics without depending on an installed system font.
        """
        # pypdf keeps this decoder in a private module; adapter regressions cover
        # it and the dependency is bounded to the supported major version.
        font = Font.from_font_resource(resource)
        decoded: dict[str, str] = {}
        if isinstance(font.encoding, dict):
            decoded.update({chr(code): char for code, char in font.encoding.items()})
        decoded.update(
            {
                code: char
                for code, char in font.character_map.items()
                if isinstance(code, str) and isinstance(char, str)
            }
        )
        widths = {decoded.get(code, code): width for code, width in font.character_widths.items()}
        widths.setdefault(" ", float(font.space_width))
        return cls(widths, font.character_widths["default"])

    def advance(self, text: str, size: float) -> float:
        """Measure decoded text in local text coordinates.

        Args:
            text: A span without synthetic newline characters.
            size: PDF font size before applying its text and user matrices.

        Returns:
            float: Horizontal advance in the current text coordinate system.
        """
        return sum(self.widths.get(char, self.default) for char in text) * size / _FONT_UNITS_PER_EM


class _PageReader:
    """Collect positioned text and each image placement in content-stream order."""

    def __init__(self, page: PageObject, number: int) -> None:
        """Keep the page's coordinate system and an initially empty visitor stack."""
        self._number = number
        rotation = Transformation().rotate(-page.rotation)
        bounds = [
            rotation.apply_on(point)
            for point in (
                page.mediabox.lower_left,
                page.mediabox.lower_right,
                page.mediabox.upper_left,
                page.mediabox.upper_right,
            )
        ]
        left, bottom = min(x for x, _ in bounds), min(y for _, y in bounds)
        self._top = max(y for _, y in bounds) - bottom
        coordinates = rotation.translate(-left, -bottom)
        self._root = _ContentSpace(_dictionary(page, "/Resources"), coordinates)
        self._operations: list[_Operation] = []
        self._text: list[TextLine] = []
        self._last_right: float | None = None
        self._fonts: dict[int, _FontWidths] = {}
        self.images: list[tuple[ImageRef, StreamObject]] = []

    @property
    def lines(self) -> list[TextLine]:
        """Return non-empty lines with whitespace trimmed after joining text spans."""
        return [TextLine(line.text.strip(), line.page, line.top) for line in self._text]

    def before_operation(
        self,
        operator: bytes,
        operands: object,
        user_matrix: list[float],
        text_matrix: list[float],
    ) -> None:
        """Track nested forms and image placements before pypdf handles an operator."""
        del text_matrix
        space = self._root
        if self._operations:
            parent = self._operations[-1]
            parent.entered = True
            space = parent.child or parent.space
        operation = _Operation(space)
        self._operations.append(operation)
        if not isinstance(operands, list):
            return None
        if operator in (b"TL", b"TD") and operands:
            space.leading = float(str(operands[-1])) * (-1 if operator == b"TD" else 1)
        if operator != b"Do" or not operands:
            return None
        objects = _dictionary(space.resources, "/XObject")
        obj = objects[str(operands[0])]
        if not isinstance(obj, StreamObject):
            raise ValueError("PDF XObject must be a stream")
        matrix = _transform(user_matrix).transform(space.transform)
        if obj.get("/Subtype") == "/Image":
            self._add_image(obj, matrix)
        elif obj.get("/Subtype") == "/Form":
            form_matrix = _transform(obj.get("/Matrix", _IDENTITY)).transform(matrix)
            resources = _dictionary(obj, "/Resources") if "/Resources" in obj else space.resources
            operation.child = _ContentSpace(resources, form_matrix)
        return None

    def after_operation(
        self,
        operator: bytes,
        operands: object,
        user_matrix: list[float],
        text_matrix: list[float],
    ) -> None:
        """Restore the enclosing coordinate space after an operator or nested form."""
        del operator, operands, user_matrix, text_matrix
        self._operations.pop()
        return None

    def visit_text(
        self,
        text: str,
        user_matrix: list[float],
        text_matrix: list[float],
        font: DictionaryObject | None,
        font_size: float,
    ) -> None:
        """Join styled spans and convert PDF bottom-up baselines to top-down positions."""
        space = self._root
        if self._operations:
            operation = self._operations[-1]
            space = operation.child if operation.entered and operation.child else operation.space
        matrix = (
            _transform(text_matrix).transform(_transform(user_matrix)).transform(space.transform)
        )
        leading = space.leading or font_size * _DEFAULT_LINE_SPACING
        if font is None:
            metrics = _FontWidths({" ": _FONT_UNITS_PER_EM / 4}, _FONT_UNITS_PER_EM / 2)
        else:
            key = id(font)
            if key not in self._fonts:
                self._fonts[key] = _FontWidths.from_resource(font)
            metrics = self._fonts[key]
        for index, part in enumerate(text.splitlines(keepends=True)):
            content = part.rstrip("\r\n")
            if content.strip():
                x, y = matrix.apply_on((0, -leading * index))
                right, _ = matrix.apply_on((metrics.advance(content, font_size), -leading * index))
                space_end, _ = matrix.apply_on((metrics.advance(" ", font_size), -leading * index))
                word_space = abs(space_end - x)
                top = self._top - y
                self._append_span(content, x, top, word_space)
                self._last_right = right
        return None

    def _append_span(self, content: str, x: float, top: float, word_space: float) -> None:
        """Join adjacent spans on one baseline while keeping distant columns apart.

        Args:
            content: Text without a synthetic newline suffix.
            x: Page-space left edge of this span.
            top: Page-space baseline measured from the top.
            word_space: Width of one space in the current transformed font.

        Returns:
            None: Appends or extends a positioned line.
        """
        if self._text and self._last_right is not None:
            previous = self._text[-1]
            gap = x - self._last_right
            max_gap = max(_LINE_TOLERANCE, word_space * _MAX_WORD_GAP_SPACES)
            if abs(previous.top - top) <= _LINE_TOLERANCE and -_LINE_TOLERANCE <= gap <= max_gap:
                separator = ""
                if gap > word_space * _WORD_GAP_RATIO and not (
                    previous.text[-1].isspace() or content[0].isspace()
                ):
                    separator = " "
                self._text[-1] = TextLine(
                    previous.text + separator + content, self._number, previous.top
                )
                return None
        self._text.append(TextLine(content, self._number, top))
        return None

    def _add_image(self, image: StreamObject, matrix: Transformation) -> None:
        """Record every painted placement, including repeated and transformed images."""
        corners = [matrix.apply_on(point) for point in ((0, 0), (1, 0), (0, 1), (1, 1))]
        reference = image.indirect_reference
        image_id = reference.idnum if reference is not None else -(len(self.images) + 1)
        ref = ImageRef(
            xref=image_id,
            page=self._number,
            top=self._top - max(y for _, y in corners),
            width=int(str(image["/Width"])),
            height=int(str(image["/Height"])),
        )
        self.images.append((ref, image))
        return None


class PdfDocument:
    """Read text and XObject images while keeping source files unchanged."""

    def __init__(self, path: Path) -> None:
        """Open and validate a PDF, rejecting files that require a password.

        Args:
            path: Source PDF; it is never modified.

        Raises:
            SourceReadError: The PDF is missing, invalid, or password-protected.
        """
        self._path = path
        self._reader: PdfReader | None = None
        self._lines: list[TextLine] | None = None
        self._images: list[ImageRef] = []
        self._objects: dict[tuple[int, int], StreamObject] = {}
        try:
            self._reader = PdfReader(path)
            if self._reader.is_encrypted and not self._reader.decrypt(""):
                raise ValueError("PDF requires a password")
            len(self._reader.pages)
        except _PDF_ERRORS as exc:
            self.close()
            raise SourceReadError(f"Cannot open PDF {path}: {exc}") from exc

    def __enter__(self) -> Self:
        """Return this document for a read-only context-managed import."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the reader, including when extraction raises an exception."""
        self.close()
        return None

    def close(self) -> None:
        """Release PDF resources; repeated calls are safe.

        Returns:
            None: The document can no longer be read.
        """
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        return None

    def lines(self) -> list[TextLine]:
        """Return non-empty text in content order with 1-based page numbers."""
        self._read_pages()
        return list(self._lines or [])

    def images(self) -> list[ImageRef]:
        """Return all painted XObject image placements, including nested forms."""
        self._read_pages()
        return list(self._images)

    def extract_image(self, ref: ImageRef) -> ImageData:
        """Decode the referenced image, retaining alpha masks and normalizing format.

        Args:
            ref: An image placement returned by this document.

        Returns:
            ImageData: JPEG for unmasked JPEG images, otherwise lossless PNG.

        Raises:
            SourceReadError: The reference is invalid or decoding is unsupported.
        """
        self._read_pages()
        try:
            obj = self._objects[(ref.page, ref.xref)]
            decoded = cast(Image.Image | None, obj.decode_as_image())
            if decoded is None:
                raise ValueError("PDF image has no supported decoder")
            with decoded:
                is_jpeg = decoded.format == "JPEG" and "/SMask" not in obj and "/Mask" not in obj
                if is_jpeg:
                    return ImageData(obj.get_data(), "jpg")
                with BytesIO() as output:
                    decoded.save(output, format="PNG")
                    return ImageData(output.getvalue(), "png")
        except _PDF_ERRORS as exc:
            raise SourceReadError(
                f"Cannot extract image {ref.xref} from PDF {self._path}: {exc}"
            ) from exc

    def _read_pages(self) -> None:
        """Cache both visitor results only after every page was extracted successfully."""
        if self._reader is None:
            raise SourceReadError(f"PDF is closed: {self._path}")
        if self._lines is not None:
            return None
        lines: list[TextLine] = []
        images: list[ImageRef] = []
        objects: dict[tuple[int, int], StreamObject] = {}
        try:
            for number, page in enumerate(self._reader.pages, start=1):
                collector = _PageReader(page, number)
                page.extract_text(
                    visitor_text=collector.visit_text,
                    visitor_operand_before=collector.before_operation,
                    visitor_operand_after=collector.after_operation,
                )
                lines.extend(collector.lines)
                for ref, obj in collector.images:
                    images.append(ref)
                    objects[(ref.page, ref.xref)] = obj
        except _PDF_ERRORS as exc:
            raise SourceReadError(f"Cannot read PDF {self._path}: {exc}") from exc
        self._lines, self._images, self._objects = lines, images, objects
        return None
