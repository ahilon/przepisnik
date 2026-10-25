"""File-based storage: one folder per recipe plus a registry of imported sources.

Layout::

    <data>/recipes/<recipe-id>/recipe.json
    <data>/recipes/<recipe-id>/image.<ext>
    <data>/sources.json
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from przepisnik.core.models import ImportedSource, Recipe, recipe_id_for, slugify
from przepisnik.errors import StoreError

if TYPE_CHECKING:
    from pathlib import Path

    from przepisnik.core.models import ImageData

RECIPES_DIR = "recipes"
RECIPE_FILE = "recipe.json"
SOURCES_FILE = "sources.json"
IMAGE_STEM = "image"

_SOURCES_ADAPTER = TypeAdapter(dict[str, ImportedSource])


class JsonRecipeStore:
    """Recipes stored as pretty-printed JSON files, one folder per recipe."""

    def __init__(self, data_dir: Path) -> None:
        """Create a store rooted at ``data_dir`` (created lazily on first save)."""
        self._recipes_dir = data_dir / RECIPES_DIR

    def get(self, recipe_id: str) -> Recipe | None:
        """Load a recipe by id.

        Raises:
            StoreError: If the stored file is not a valid recipe.
        """
        path = self._recipes_dir / recipe_id / RECIPE_FILE
        if not path.is_file():
            return None
        try:
            return Recipe.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise StoreError(f"Invalid recipe file {path}: {exc}") from exc

    def versions(self, title: str) -> list[Recipe]:
        """Return all stored versions of recipes with this title, ordered by version."""
        base = slugify(title)
        result: list[Recipe] = []
        version = 1
        while (recipe := self.get(recipe_id_for(title, version))) is not None:
            if slugify(recipe.title) == base:
                result.append(recipe)
            version += 1
        return result

    def save(self, recipe: Recipe, image: ImageData | None = None) -> Recipe:
        """Write a recipe and, optionally, its dish photo.

        Args:
            recipe: Recipe to store.
            image: Photo to store; replaces the previous one.

        Returns:
            The stored recipe, with ``image`` pointing at the saved photo.
        """
        directory = self._recipes_dir / recipe.id
        directory.mkdir(parents=True, exist_ok=True)
        if image is not None:
            image_name = f"{IMAGE_STEM}.{image.extension}"
            (directory / image_name).write_bytes(image.content)
            recipe = recipe.model_copy(update={"image": image_name})
        _write_atomically(directory / RECIPE_FILE, recipe.model_dump_json(indent=2))
        return recipe


class JsonSourceRegistry:
    """Registry of imported sources keyed by file hash or URL."""

    def __init__(self, data_dir: Path) -> None:
        """Create a registry stored in ``<data_dir>/sources.json``."""
        self._path = data_dir / SOURCES_FILE

    def find(self, key: str) -> ImportedSource | None:
        """Return the registry entry for a source key, if any."""
        return self._load().get(key)

    def register(self, entry: ImportedSource) -> None:
        """Add or replace the registry entry of a source."""
        entries = self._load()
        entries[entry.key] = entry
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = _SOURCES_ADAPTER.dump_json(entries, indent=2).decode("utf-8")
        _write_atomically(self._path, payload)

    def _load(self) -> dict[str, ImportedSource]:
        if not self._path.is_file():
            return {}
        try:
            return _SOURCES_ADAPTER.validate_json(self._path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise StoreError(f"Invalid source registry {self._path}: {exc}") from exc


def _write_atomically(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text + "\n", encoding="utf-8")
    temporary.replace(path)
