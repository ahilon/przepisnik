"""Explicit, transactional migration from legacy JSON without changing its files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from przepisnik.core.database import SqliteStore
from przepisnik.core.identity import content_fingerprint
from przepisnik.core.models import ImportedSource, Recipe
from przepisnik.errors import StoreError

if TYPE_CHECKING:
    from pathlib import Path


def migrate_json(data_dir: Path, *, dry_run: bool = False) -> dict[str, int]:
    """Copy legacy recipes and sources; refuse any existing differing ID.

    Original JSON and images stay in place. Repeating a completed migration is safe.
    """
    paths = sorted((data_dir / "recipes").glob("*/recipe.json"))
    recipes = [Recipe.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]
    registry = data_dir / "sources.json"
    sources = (
        TypeAdapter(dict[str, ImportedSource]).validate_json(registry.read_text(encoding="utf-8"))
        if registry.exists()
        else {}
    )
    counts = {"created": 0, "unchanged": 0, "variants": 0, "sources": len(sources)}
    with SqliteStore(data_dir, read_only=dry_run) as store, store.transaction():
        for recipe in recipes:
            existing = store.get(recipe.id)
            if existing and existing.model_dump(
                exclude={"created_at", "updated_at"}
            ) != recipe.model_dump(exclude={"created_at", "updated_at"}):
                raise StoreError(
                    f"Migration would replace existing recipe {recipe.id}; nothing imported"
                )
            counts["unchanged" if existing else "created"] += 1
            counts["variants"] += len(recipe.variants)
            if dry_run:
                continue
            if existing is None:
                store.save(recipe)
            for kind, variant in recipe.variants.items():
                if variant.source is not None:
                    source = variant.source
                    key = source.sha256 or source.url or source.file
                    if key:
                        store.remember(
                            key,
                            content_fingerprint(recipe.title, variant, recipe.steps_for(kind)),
                            kind,
                            recipe.id,
                        )
        if not dry_run:
            for entry in sources.values():
                if store.find(entry.key) is None:
                    store.register(entry)
            store.mark_legacy_migrated()
    return counts
