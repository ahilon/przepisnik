"""Resolve explicitly named source folders to recipe variants."""

import tomllib
from collections.abc import Sequence
from pathlib import Path

from przepisnik.core.models import VariantKind

DEFAULT_ALIASES = {
    "kobieta": VariantKind.FEMALE,
    "female": VariantKind.FEMALE,
    "mezczyzna": VariantKind.MALE,
    "mężczyzna": VariantKind.MALE,
    "male": VariantKind.MALE,
    "rodzina": VariantKind.FAMILY,
    "family": VariantKind.FAMILY,
}


class VariantAliases:
    """Match folder labels without guessing a person's variant from their name."""

    def __init__(self, config: Path | None = None, overrides: Sequence[str] = ()) -> None:
        """Load defaults, an optional TOML mapping and explicit CLI overrides.

        Args:
            config: Optional TOML file containing an aliases table.
            overrides: Explicit folder=variant mappings, applied after configuration.

        Returns:
            None: Stores the validated case-insensitive mapping.

        Raises:
            ValueError: If configuration or an alias is malformed.
        """
        self._values = dict(DEFAULT_ALIASES)
        if config is not None:
            with config.open("rb") as source:
                document = tomllib.load(source)
            values = document.get("aliases")
            if set(document) != {"aliases"} or not isinstance(values, dict):
                raise ValueError("Alias configuration must contain only an [aliases] table")
            for name, variant in values.items():
                if not isinstance(variant, str):
                    raise ValueError("Alias values must be variant names")
                self._set(name, variant)
        for override in overrides:
            name, separator, variant = override.partition("=")
            if not separator:
                raise ValueError("Use --alias folder=female|male|family")
            self._set(name, variant)
        return None

    def _set(self, name: str, variant: str) -> None:
        """Validate and store one folder label.

        Args:
            name: A single directory name, not a path.
            variant: One canonical variant name.

        Returns:
            None: The explicit alias replaces any previous mapping for that label.
        """
        label = name.strip().casefold()
        if not label or label in {".", ".."} or any(part in label for part in ("/", "\\")):
            raise ValueError("An alias must be one non-empty folder name")
        self._values[label] = VariantKind(variant)
        return None

    def resolve(self, labels: Sequence[str], fallback: VariantKind | None = None) -> VariantKind:
        """Resolve folder ancestry, rejecting missing or contradictory assignments.

        Args:
            labels: Root and ancestor directory labels for one PDF.
            fallback: Explicit variant for files without a recognized folder label.

        Returns:
            VariantKind: Exactly one explicitly assigned variant.

        Raises:
            ValueError: If folder mappings conflict or no variant was supplied.
        """
        matches = {
            self._values[label.casefold()] for label in labels if label.casefold() in self._values
        }
        if len(matches) > 1:
            raise ValueError(f"Contradictory variant folders: {'/'.join(labels)}")
        if matches:
            return next(iter(matches))
        if fallback is not None:
            return fallback
        location = "/".join(labels)
        raise ValueError(f"No variant assigned to {location}; provide an alias or --variant")
