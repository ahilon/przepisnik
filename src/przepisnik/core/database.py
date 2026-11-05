"""SQLite persistence with validated recipe snapshots and durable import identities.

Recipe documents retain the nested public Pydantic schema. Relational indexes track
stable IDs, title lookup, sources and consumed source content independently of edits.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from przepisnik.core.models import ImportedSource, Recipe, VariantKind, slugify, utc_now
from przepisnik.core.schema import initialize_schema
from przepisnik.errors import StoreError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from przepisnik.core.models import ImageData

DATABASE_NAME = "recipes.sqlite3"
IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "webp", "gif", "bmp"})


class SqliteStore:
    """Shared recipe store, source registry and import ledger for CLI and future UI."""

    def __init__(self, data_dir: Path, *, read_only: bool = False) -> None:
        """Open the database; previews of a missing database use memory only."""
        self.data_dir = data_dir
        path = data_dir / DATABASE_NAME
        self._read_only = read_only
        try:
            if read_only:
                self._connection = sqlite3.connect(
                    f"{path.resolve().as_uri()}?mode=ro" if path.exists() else ":memory:",
                    uri=path.exists(),
                )
            else:
                data_dir.mkdir(parents=True, exist_ok=True)
                self._connection = sqlite3.connect(path)
            self._connection.execute("PRAGMA foreign_keys = ON")
            initialize_schema(self._connection, path, read_only=read_only and path.exists())
        except (sqlite3.Error, OSError) as exc:
            raise StoreError(f"Cannot open database {path}: {exc}") from exc

    def __enter__(self) -> SqliteStore:
        """Return the open store."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Close the connection, rolling back an unfinished transaction."""
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit a whole operation or roll it back on any failure."""
        try:
            self._connection.execute("BEGIN" if self._read_only else "BEGIN IMMEDIATE")
            yield
            self._connection.commit()
        except (sqlite3.Error, OSError) as exc:
            self._connection.rollback()
            raise StoreError(f"Database operation failed: {exc}") from exc
        except BaseException:
            self._connection.rollback()
            raise

    def get(self, recipe_id: str) -> Recipe | None:
        """Load a recipe by stable ID."""
        row = self._connection.execute(
            "SELECT payload FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        return self._recipe(row[0]) if row else None

    def all(self) -> list[Recipe]:
        """Return all validated recipes in stable ID order."""
        return [
            self._recipe(row[0])
            for row in self._connection.execute("SELECT payload FROM recipes ORDER BY id")
        ]

    def integrity_errors(self) -> list[str]:
        """Check SQLite structures and foreign keys without changing data."""
        errors = [
            str(row[0])
            for row in self._connection.execute("PRAGMA integrity_check")
            if row[0] != "ok"
        ]
        errors.extend(
            f"Foreign key violation: {row}"
            for row in self._connection.execute("PRAGMA foreign_key_check")
        )
        return errors

    def versions(self, title: str) -> list[Recipe]:
        """Find all versions by current title, independent of their stable IDs."""
        rows = self._connection.execute(
            "SELECT payload FROM recipes WHERE title_key = ?", (slugify(title),)
        )
        return sorted((self._recipe(row[0]) for row in rows), key=lambda recipe: recipe.version)

    def save(self, recipe: Recipe, image: ImageData | None = None) -> Recipe:
        """Save changed validated content, preserving timestamps for unchanged recipes."""
        current = self.get(recipe.id)
        changes: dict[str, object] = {
            "created_at": current.created_at if current else recipe.created_at,
        }
        if image is not None:
            changes["image"] = self._save_image(
                recipe.id, image, current.image if current else None
            )
        validated = Recipe.model_validate({**recipe.model_dump(), **changes})
        timestamps = {"created_at", "updated_at"}
        if current and validated.model_dump(exclude=timestamps) == current.model_dump(
            exclude=timestamps
        ):
            return current
        now = utc_now()
        validated = validated.model_copy(
            update={"created_at": validated.created_at or now, "updated_at": now}
        )
        self._connection.execute(
            "INSERT INTO recipes(id, title_key, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title_key=excluded.title_key, payload=excluded.payload",
            (validated.id, slugify(validated.title), validated.model_dump_json()),
        )
        return validated

    def find(self, key: str) -> ImportedSource | None:
        """Find a source registry entry."""
        row = self._connection.execute(
            "SELECT payload FROM sources WHERE key = ?", (key,)
        ).fetchone()
        return ImportedSource.model_validate_json(row[0]) if row else None

    def register(self, entry: ImportedSource) -> None:
        """Update source metadata inside the current transaction."""
        self._connection.execute(
            "INSERT INTO sources(key, payload) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
            (entry.key, entry.model_dump_json()),
        )

    def imported(self, fingerprint: str, kind: VariantKind) -> str | None:
        """Find consumed source content even after manual edits or variant moves."""
        row = self._connection.execute(
            "SELECT recipe_id FROM imported_items "
            "WHERE fingerprint = ? AND original_variant = ? LIMIT 1",
            (fingerprint, kind.value),
        ).fetchone()
        return str(row[0]) if row else None

    def remember(
        self, source_key: str, fingerprint: str, kind: VariantKind, recipe_id: str
    ) -> None:
        """Keep original import identity separately from the current assignment."""
        self._connection.execute(
            "INSERT OR IGNORE INTO imported_items"
            "(source_key, fingerprint, original_variant, recipe_id) VALUES (?, ?, ?, ?)",
            (source_key, fingerprint, kind.value, recipe_id),
        )

    def legacy_migrated(self) -> bool:
        """Return whether legacy migration completed successfully."""
        return (
            self._connection.execute(
                "SELECT 1 FROM app_state WHERE key = 'legacy_migrated'"
            ).fetchone()
            is not None
        )

    def get_state(self, key: str) -> str | None:
        """Read an application-owned value independently of recipe records."""
        row = self._connection.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)
        ).fetchone()
        return str(row[0]) if row else None

    def set_state(self, key: str, value: str) -> None:
        """Write application state within the caller's transaction."""
        self._connection.execute(
            "INSERT INTO app_state(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE value != excluded.value",
            (key, value),
        )

    def mark_legacy_migrated(self) -> None:
        """Mark completion inside the same transaction as migrated recipes."""
        self._connection.execute(
            "INSERT OR IGNORE INTO app_state(key, value) VALUES ('legacy_migrated', '1')"
        )

    def _save_image(self, recipe_id: str, image: ImageData, existing: str | None = None) -> str:
        extension = image.extension.lower()
        if extension not in IMAGE_EXTENSIONS:
            raise StoreError(f"Unsupported image extension: {extension}")
        directory = self.data_dir / "recipes" / recipe_id
        if existing:
            current_path = directory / existing
            if current_path.is_file() and current_path.read_bytes() == image.content:
                return existing
        digest = hashlib.sha256(image.content).hexdigest()
        name = f"image-{digest}.{extension}"
        directory.mkdir(parents=True, exist_ok=True)
        # Content-addressed files never overwrite a photo referenced by committed data.
        path = directory / name
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise StoreError(f"Stored image is corrupted: {path}")
        else:
            path.write_bytes(image.content)
        return name

    @staticmethod
    def _recipe(payload: str) -> Recipe:
        try:
            return Recipe.model_validate_json(payload)
        except ValidationError as exc:
            raise StoreError(f"Invalid recipe in database: {exc}") from exc
