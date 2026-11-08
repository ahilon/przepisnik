"""Check SQLite persistence, timestamps, images, transactions and the import ledger."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factories import PNG_BYTES, recipe

from przepisnik.core.database import DATABASE_NAME, SqliteStore
from przepisnik.core.models import ImageData, ImportedSource, UserMetadata, VariantKind
from przepisnik.errors import StoreError


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteStore]:
    """Return a writable store in an empty temporary directory."""
    with SqliteStore(tmp_path / "data") as opened:
        yield opened


def test_save_sets_timestamps_and_skips_unchanged_content(store: SqliteStore) -> None:
    """Keep timestamps for no-op saves and refresh only updated_at on changes."""
    created = store.save(recipe())
    assert created.created_at is not None
    assert created.updated_at == created.created_at
    assert store.save(recipe()) == created
    changed = store.save(created.model_copy(update={"user": UserMetadata(favorite=True)}))
    assert changed.created_at == created.created_at
    assert changed.updated_at is not None
    assert changed.updated_at >= created.updated_at
    assert store.get(created.id) == changed


def test_queries_return_validated_recipes(store: SqliteStore) -> None:
    """Find recipes by ID, list them in ID order and group versions by title."""
    second = recipe(names=["Kasza"], version=2)
    store.save(second)
    store.save(recipe())
    store.save(recipe("Bajgiel"))
    assert store.get("missing") is None
    assert [item.id for item in store.all()] == [
        "bajgiel",
        "ryz-z-kurczakiem",
        "ryz-z-kurczakiem-2",
    ]
    assert [item.version for item in store.versions("RYŻ Z KURCZAKIEM")] == [1, 2]
    assert store.integrity_errors() == []


def test_image_is_stored_by_content_hash(store: SqliteStore) -> None:
    """Write each image once and keep the existing name for identical uploads."""
    saved = store.save(recipe(), ImageData(PNG_BYTES, "PNG"))
    assert saved.image is not None
    assert saved.image.startswith("image-")
    assert saved.image.endswith(".png")
    image_path = store.data_dir / "recipes" / saved.id / saved.image
    assert image_path.read_bytes() == PNG_BYTES
    assert store.save(saved, ImageData(PNG_BYTES, "png")) == saved


def test_unsupported_image_extension_is_rejected(store: SqliteStore) -> None:
    """Accept only raster image extensions."""
    with pytest.raises(StoreError, match="Unsupported image"):
        store.save(recipe(), ImageData(b"<svg/>", "svg"))


def test_corrupted_image_file_is_detected(store: SqliteStore) -> None:
    """Refuse to reference a content-addressed file whose bytes changed."""
    saved = store.save(recipe(), ImageData(PNG_BYTES, "png"))
    assert saved.image is not None
    (store.data_dir / "recipes" / saved.id / saved.image).write_bytes(b"broken")
    with pytest.raises(StoreError, match="corrupted"):
        store.save(saved, ImageData(PNG_BYTES, "png"))


def test_transaction_rolls_back_on_error(store: SqliteStore) -> None:
    """Discard all writes of a failed operation."""
    with pytest.raises(RuntimeError), store.transaction():
        store.save(recipe())
        raise RuntimeError
    assert store.all() == []


def test_sqlite_errors_become_store_errors(store: SqliteStore) -> None:
    """Report database failures as expected, user-facing errors."""
    with pytest.raises(StoreError, match="Database operation failed"), store.transaction():
        store.remember("source", "fingerprint", VariantKind.FEMALE, "missing-recipe")


def test_read_only_store_cannot_write(tmp_path: Path) -> None:
    """Open existing databases read-only and reject writes."""
    with SqliteStore(tmp_path) as store, store.transaction():
        store.save(recipe())
    with SqliteStore(tmp_path, read_only=True) as store:
        assert len(store.all()) == 1
        with pytest.raises(StoreError), store.transaction():
            store.save(recipe("Inny"))


def test_read_only_preview_of_missing_database_uses_memory(tmp_path: Path) -> None:
    """Previewing a new data directory creates no files."""
    data_dir = tmp_path / "new"
    with SqliteStore(data_dir, read_only=True) as store:
        assert store.all() == []
    assert not data_dir.exists()


def test_invalid_stored_recipe_is_reported(tmp_path: Path) -> None:
    """Surface documents that no longer match the schema."""
    with SqliteStore(tmp_path):
        pass
    with closing(sqlite3.connect(tmp_path / DATABASE_NAME)) as connection, connection:
        connection.execute(
            "INSERT INTO recipes(id, title_key, payload) VALUES ('bad', 'bad', '{}')"
        )
    with SqliteStore(tmp_path) as store, pytest.raises(StoreError, match="Invalid recipe"):
        store.get("bad")


def test_unopenable_database_is_reported(tmp_path: Path) -> None:
    """Wrap filesystem and SQLite failures while opening."""
    (tmp_path / DATABASE_NAME).write_bytes(b"not a database" * 100)
    with pytest.raises(StoreError, match="Cannot open database"):
        SqliteStore(tmp_path)


def test_sources_ledger_and_state(store: SqliteStore) -> None:
    """Persist source entries, consumed fingerprints and application state."""
    entry = ImportedSource(
        key="sha",
        name="plan.pdf",
        parser="respo",
        variant=VariantKind.FEMALE,
        imported_at=datetime(2026, 1, 1, tzinfo=UTC),
        recipe_count=3,
    )
    with store.transaction():
        saved = store.save(recipe())
        store.register(entry)
        store.register(entry.model_copy(update={"recipe_count": 4}))
        store.remember("sha", "fp", VariantKind.FEMALE, saved.id)
        store.remember("sha", "fp", VariantKind.FEMALE, saved.id)
        store.set_state("key", "value")
        store.set_state("key", "value")
        store.mark_legacy_migrated()
    found = store.find("sha")
    assert found is not None
    assert found.recipe_count == 4
    assert store.find("other") is None
    assert store.imported("fp", VariantKind.FEMALE) == saved.id
    assert store.imported("fp", VariantKind.MALE) is None
    assert store.get_state("key") == "value"
    assert store.get_state("missing") is None
    assert store.legacy_migrated() is True
