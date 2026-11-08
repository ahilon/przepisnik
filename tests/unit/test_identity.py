"""Check that import fingerprints follow content, not formatting or provenance."""

from factories import draft, variant_data

from przepisnik.core.identity import content_fingerprint, draft_fingerprint
from przepisnik.core.models import Ingredient, Source, Variant, VariantData


def _fingerprint(variant: VariantData, steps: list[str], title: str = "Ryż z kurczakiem") -> str:
    return content_fingerprint(title, variant, steps)


def test_fingerprint_ignores_formatting_order_and_provenance() -> None:
    """Raw text, ingredient order, title spelling, step spacing and sources do not matter."""
    base = variant_data(["Ryż", "Kurczak"])
    reordered = Variant(
        **{
            **dict(variant_data(["Kurczak", "Ryż"])),
            "ingredients": [
                Ingredient(name="kurczak", metric_amount=100, metric_unit="g", raw="Kurczak 100g"),
                Ingredient(name="RYŻ", metric_amount=100, metric_unit="g"),
            ],
        },
        source=Source(parser="respo", page=3),
    )
    assert _fingerprint(base, ["Ugotuj ryż."]) == _fingerprint(
        reordered, ["  Ugotuj   ryż. "], title="RYZ Z KURCZAKIEM"
    )


def test_fingerprint_changes_with_content() -> None:
    """Different quantities, servings, nutrition, steps or titles are different content."""
    base = _fingerprint(variant_data(), ["Ugotuj ryż."])
    changed = [
        _fingerprint(variant_data(["Ryż"]), ["Ugotuj ryż."]),
        _fingerprint(variant_data(kcal=500), ["Ugotuj ryż."]),
        _fingerprint(variant_data(servings=2), ["Ugotuj ryż."]),
        _fingerprint(variant_data(), ["Ugotuj kaszę."]),
        _fingerprint(variant_data(), ["Ugotuj ryż."], title="Kasza z kurczakiem"),
    ]
    assert base not in changed
    assert len(set(changed)) == len(changed)


def test_draft_fingerprint_matches_content_fingerprint() -> None:
    """Use the same identity for drafts and stored variants."""
    item = draft()
    assert draft_fingerprint(item) == content_fingerprint(item.title, item.variant, item.steps)
