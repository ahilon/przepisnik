"""Deterministic recipe identities, independent of metadata and variant assignment."""

from __future__ import annotations

import hashlib
import json

from przepisnik.core.models import RecipeDraft, VariantData, slugify


def content_fingerprint(title: str, variant: VariantData, steps: list[str]) -> str:
    """Identify content without raw formatting, provenance or user metadata."""
    ingredients = []
    for ingredient in variant.ingredients:
        item = ingredient.model_dump(exclude={"raw"})
        item["name"] = slugify(ingredient.name)
        ingredients.append(item)
    payload = {
        "title": slugify(title),
        "servings": variant.servings,
        "nutrition": variant.nutrition.model_dump() if variant.nutrition else None,
        "ingredients": sorted(ingredients, key=lambda item: json.dumps(item, sort_keys=True)),
        "steps": [" ".join(step.split()) for step in steps],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def draft_fingerprint(draft: RecipeDraft) -> str:
    """Return the import identity of one extracted recipe."""
    return content_fingerprint(draft.title, draft.variant, draft.steps)
