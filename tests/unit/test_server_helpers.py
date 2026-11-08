"""Check upload decoding and response helpers of the recipe browser."""

import base64
import binascii

import pytest
from factories import PNG_BYTES, recipe

from przepisnik.core.models import ImageData, UserMetadata
from przepisnik.web import server
from przepisnik.web.server import _image_url, _summary, _uploaded_image


def _encode(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


@pytest.mark.parametrize(
    ("content", "extension"),
    [
        (PNG_BYTES, "png"),
        (b"\xff\xd8\xff\xe0jpeg", "jpg"),
        (b"GIF89a....", "gif"),
        (b"GIF87a....", "gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
    ],
)
def test_uploads_are_recognised_by_magic_bytes(content: bytes, extension: str) -> None:
    """Derive the extension from file content, not a client-supplied name."""
    assert _uploaded_image(_encode(content)) == ImageData(content, extension)


def test_missing_upload_means_no_image() -> None:
    """Keep the current image when nothing is uploaded."""
    assert _uploaded_image(None) is None


@pytest.mark.parametrize(
    "value",
    [123, "", _encode(b"<svg></svg>"), _encode(b"%PDF-1.7")],
)
def test_invalid_uploads_are_rejected(value: object) -> None:
    """Refuse non-strings, empty files and non-raster formats."""
    with pytest.raises(ValueError, match=r"(?i)image"):
        _uploaded_image(value)


def test_upload_must_be_strict_base64() -> None:
    """Reject characters outside the base64 alphabet."""
    with pytest.raises(binascii.Error):
        _uploaded_image("not base64!")


def test_upload_size_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse images above the configured limit."""
    monkeypatch.setattr(server, "MAX_IMAGE_BYTES", len(PNG_BYTES) - 1)
    with pytest.raises(ValueError, match="exceeds"):
        _uploaded_image(_encode(PNG_BYTES))


def test_summary_uses_effective_fields_and_placeholder_image() -> None:
    """List effective categories, flags and the image endpoint."""
    plain = recipe().model_copy(
        update={"user": UserMetadata(favorite=True, tags=["Szybkie"], preparation_minutes=15)}
    )
    assert _image_url(plain) == "/empty_dish.png"
    assert _summary(plain) == {
        "id": "ryz-z-kurczakiem",
        "title": "Ryż z kurczakiem",
        "image_url": "/empty_dish.png",
        "meal_types": [],
        "dish_types": [],
        "variants": ["female"],
        "favorite": True,
        "hidden": False,
        "minutes": 15,
        "tags": ["Szybkie"],
    }
    with_photo = plain.model_copy(update={"image": "image-abc.png"})
    assert _image_url(with_photo) == "/images/ryz-z-kurczakiem"
