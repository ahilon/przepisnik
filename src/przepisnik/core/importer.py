"""Use case: import recipes extracted from one source as one variant.

This is the single entry point through which every source - code parsers and
agent-written drafts alike - reaches the JSON store.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

from przepisnik.core.merge import MergeOutcome, merge_variant
from przepisnik.core.models import ImportedSource, Recipe, Source, VariantKind, slugify
from przepisnik.errors import SourceAlreadyImportedError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from przepisnik.core.models import ImageData, RecipeDraft


class RecipeStore(Protocol):
    """Persistence of recipes."""

    def versions(self, title: str) -> list[Recipe]:
        """Return stored versions of recipes with this title, ordered by version."""
        ...

    def save(self, recipe: Recipe, image: ImageData | None = None) -> Recipe:
        """Store a recipe and optionally its photo; return the stored recipe."""
        ...


class SourceRegistry(Protocol):
    """Registry of already imported sources."""

    def find(self, key: str) -> ImportedSource | None:
        """Return the entry for a source key, if any."""
        ...

    def register(self, entry: ImportedSource) -> None:
        """Record an imported source."""
        ...


@dataclass(frozen=True, slots=True)
class ExtractedRecipe:
    """Recipe draft with its location and dish photo, as found in a source."""

    draft: RecipeDraft
    page: int | None = None
    image: ImageData | None = None


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Identity of the source recipes were extracted from."""

    parser: str
    name: str
    sha256: str | None = None
    url: str | None = None

    @property
    def key(self) -> str:
        """Return the registry key: file hash, else URL, else name."""
        return self.sha256 or self.url or self.name


@dataclass(frozen=True, slots=True)
class ImportOptions:
    """Behaviour switches of an import run."""

    replace: bool = False
    dry_run: bool = False


class Conflict(BaseModel):
    """Recipe that was not imported because stored data differs."""

    recipe_id: str
    title: str
    page: int | None
    reason: str


class ImportReport(BaseModel):
    """Summary of an import run, printed as JSON for the user or agent."""

    source: str
    parser: str
    variant: VariantKind
    dry_run: bool
    counts: dict[MergeOutcome, int]
    new_versions: list[str] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecipeImporter:
    """Merge extracted recipes into the store as a single variant."""

    def __init__(self, store: RecipeStore, registry: SourceRegistry) -> None:
        """Create an importer working on the given store and source registry."""
        self._store = store
        self._registry = registry

    def run(
        self,
        recipes: Sequence[ExtractedRecipe],
        kind: VariantKind,
        origin: SourceRef,
        options: ImportOptions,
    ) -> ImportReport:
        """Import recipes extracted from one source.

        Args:
            recipes: Recipes extracted from the source.
            kind: Variant all recipes of this source represent.
            origin: Source identity.
            options: Replace and dry-run switches.

        Returns:
            Counts per merge outcome, created versions and conflicts.

        Raises:
            SourceAlreadyImportedError: If the source was imported before and
                ``options.replace`` is not set.
        """
        previous = self._registry.find(origin.key)
        if previous is not None and not options.replace:
            raise SourceAlreadyImportedError(
                f"{origin.name} was already imported as '{previous.variant}' "
                f"from {previous.name} on {previous.imported_at:%Y-%m-%d}; use --replace "
                "to import it again."
            )

        pending: dict[str, Recipe] = {}
        counts: Counter[MergeOutcome] = Counter()
        new_versions: list[str] = []
        conflicts: list[Conflict] = []
        for item in recipes:
            source = Source(
                parser=origin.parser,
                file=None if origin.url else origin.name,
                url=origin.url,
                sha256=origin.sha256,
                page=item.page,
            )
            versions = self._versions(item.draft.title, pending)
            result = merge_variant(versions, item.draft, kind, source, replace=options.replace)
            counts[result.outcome] += 1
            if result.outcome is MergeOutcome.CONFLICT:
                conflicts.append(
                    Conflict(
                        recipe_id=result.recipe.id,
                        title=item.draft.title,
                        page=item.page,
                        reason=result.reason or "",
                    )
                )
                continue
            if result.outcome is MergeOutcome.UNCHANGED:
                continue
            if result.outcome is MergeOutcome.NEW_VERSION:
                new_versions.append(result.recipe.id)
            recipe = result.recipe
            needs_image = recipe.image is None or result.outcome is MergeOutcome.REPLACED
            if not options.dry_run:
                recipe = self._store.save(recipe, item.image if needs_image else None)
            pending[recipe.id] = recipe

        if not options.dry_run:
            self._registry.register(
                ImportedSource(
                    key=origin.key,
                    name=origin.name,
                    parser=origin.parser,
                    variant=kind,
                    imported_at=datetime.now(UTC),
                    recipe_count=len(recipes),
                )
            )
        return ImportReport(
            source=origin.name,
            parser=origin.parser,
            variant=kind,
            dry_run=options.dry_run,
            counts=dict(counts),
            new_versions=new_versions,
            conflicts=conflicts,
        )

    def _versions(self, title: str, pending: dict[str, Recipe]) -> list[Recipe]:
        """Return stored versions overlaid with recipes changed earlier in this run."""
        base = slugify(title)
        merged = {recipe.id: recipe for recipe in self._store.versions(title)}
        merged.update({rid: r for rid, r in pending.items() if slugify(r.title) == base})
        return sorted(merged.values(), key=lambda recipe: recipe.version)
