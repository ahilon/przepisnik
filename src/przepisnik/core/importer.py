"""Use case: import recipes extracted from one source as one variant.

This is the single entry point through which every source - code parsers and
agent-written drafts alike - reaches the database.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

from przepisnik.core.identity import draft_fingerprint
from przepisnik.core.merge import MergeOutcome, merge_variant
from przepisnik.core.models import ImportedSource, Recipe, RecipeDraft, Source, VariantKind, slugify

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AbstractContextManager

    from przepisnik.core.models import ImageData


class RecipeStore(Protocol):
    """Persistence of recipes."""

    def versions(self, title: str) -> list[Recipe]:
        """Return stored versions of recipes with this title, ordered by version."""
        ...

    def get(self, recipe_id: str) -> Recipe | None:
        """Load a stored recipe."""
        ...

    def transaction(self) -> AbstractContextManager[None]:
        """Wrap an entire import in a transaction."""
        ...

    def imported(self, fingerprint: str, kind: VariantKind) -> str | None:
        """Look up original import identity."""
        ...

    def remember(
        self, source_key: str, fingerprint: str, kind: VariantKind, recipe_id: str
    ) -> None:
        """Record successfully consumed source content."""
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

    dry_run: bool = False
    enrich_meals: bool = False


class Conflict(BaseModel):
    """Recipe that was not imported because stored data differs."""

    recipe_id: str
    title: str
    page: int | None
    reason: str
    candidate_ids: list[str] = Field(default_factory=list)
    incoming: RecipeDraft


class ImportReport(BaseModel):
    """Summary of an import run, printed as JSON for the user or agent."""

    source: str
    parser: str
    variant: VariantKind
    dry_run: bool
    counts: dict[MergeOutcome, int]
    enriched_meals: list[str] = Field(default_factory=list)
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
            options: Preview and optional source-category enrichment switches.

        Returns:
            Counts per merge outcome, category enrichment and conflicts.

        The whole operation is transactional. Conflicts remain unconsumed and can
        be reviewed and retried; successful items are individually idempotent.
        """
        with self._store.transaction():
            return self._run(recipes, kind, origin, options)

    def _run(
        self,
        recipes: Sequence[ExtractedRecipe],
        kind: VariantKind,
        origin: SourceRef,
        options: ImportOptions,
    ) -> ImportReport:

        pending: dict[str, Recipe] = {}
        counts: Counter[MergeOutcome] = Counter()
        enriched_meals: list[str] = []
        consumed: dict[str, str] = {}
        created_ids: set[str] = set()
        conflicts: list[Conflict] = []
        for item in recipes:
            fingerprint = draft_fingerprint(item.draft)
            consumed_id = consumed.get(fingerprint) or self._store.imported(fingerprint, kind)
            if consumed_id:
                recipe = pending.get(consumed_id) or self._store.get(consumed_id)
                if recipe is not None:
                    counts[MergeOutcome.UNCHANGED] += 1
                    recipe = self._enrich(recipe, item.draft, options, enriched_meals)
                    if recipe.id in created_ids:
                        recipe = self._enrich(
                            recipe,
                            item.draft,
                            ImportOptions(dry_run=options.dry_run, enrich_meals=True),
                            enriched_meals,
                        )
                    pending[recipe.id] = recipe
                    if not options.dry_run:
                        self._store.remember(origin.key, fingerprint, kind, recipe.id)
                    continue
            source = Source(
                parser=origin.parser,
                file=None if origin.url else origin.name,
                url=origin.url,
                sha256=origin.sha256,
                page=item.page,
                meal_label=item.draft.meal_label,
                meal_type=next(iter(item.draft.meal_types), None),
                meal_type_basis=item.draft.meal_type_basis,
            )
            versions = self._versions(item.draft.title, pending)
            result = merge_variant(versions, item.draft, kind, source)
            counts[result.outcome] += 1
            if result.outcome is MergeOutcome.CONFLICT:
                conflicts.append(
                    Conflict(
                        recipe_id=result.recipe.id,
                        title=item.draft.title,
                        page=item.page,
                        reason=result.reason or "",
                        candidate_ids=[recipe.id for recipe in versions],
                        incoming=item.draft,
                    )
                )
                continue
            recipe = result.recipe
            if result.outcome is MergeOutcome.CREATED:
                created_ids.add(recipe.id)
            if result.outcome is not MergeOutcome.UNCHANGED and not options.dry_run:
                recipe = self._store.save(recipe, item.image if recipe.image is None else None)
            recipe = self._enrich(recipe, item.draft, options, enriched_meals)
            pending[recipe.id] = recipe
            consumed[fingerprint] = recipe.id
            if not options.dry_run:
                self._store.remember(origin.key, fingerprint, kind, recipe.id)

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
            enriched_meals=list(dict.fromkeys(enriched_meals)),
            conflicts=conflicts,
        )

    def _enrich(
        self,
        recipe: Recipe,
        draft: RecipeDraft,
        options: ImportOptions,
        enriched: list[str],
    ) -> Recipe:
        if not options.enrich_meals:
            return recipe
        meals = list(dict.fromkeys([*recipe.meal_types, *draft.meal_types]))
        if meals == recipe.meal_types:
            return recipe
        updated = recipe.model_copy(update={"meal_types": meals})
        enriched.append(recipe.id)
        return updated if options.dry_run else self._store.save(updated)

    def _versions(self, title: str, pending: dict[str, Recipe]) -> list[Recipe]:
        """Return stored versions overlaid with recipes changed earlier in this run."""
        base = slugify(title)
        merged = {recipe.id: recipe for recipe in self._store.versions(title)}
        merged.update({rid: r for rid, r in pending.items() if slugify(r.title) == base})
        return sorted(merged.values(), key=lambda recipe: recipe.version)
