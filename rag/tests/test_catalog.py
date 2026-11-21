import pytest

from app.catalog import SourceOutsideCatalogError, load_catalog, qualify, resolve_entry
from app.models import SourceIn

BASE = {"documentId": "d1", "title": "t", "publisher": "p", "fetchedAt": "2026-11-20", "topicTag": "prawo"}


def test_catalog_file_is_valid_and_covers_required_source_types():
    catalog = load_catalog()
    assert {entry.source_type for entry in catalog.entries} >= {"official", "factcheck", "secondary"}
    assert all(entry.qualification for entry in catalog.entries)
    assert {"official", "factcheck", "secondary", "outside_catalog", "exclusion"} <= set(catalog.rules)


def test_longest_domain_match_wins():
    isap = resolve_entry("https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU19970780483")
    assert isap.publisher.startswith("ISAP")
    assert resolve_entry("https://www.gov.pl/web/rcb/alert").source_type == "official"
    assert resolve_entry("https://demagog.org.pl/wypowiedzi/x").source_type == "factcheck"
    assert resolve_entry("https://example.org/a") is None
    assert resolve_entry("https://notgov.pl/a") is None


def test_catalog_fills_metadata_for_known_domain():
    qualified = qualify(SourceIn.model_validate({**BASE, "url": "https://www.gov.pl/web/mswia/komunikat"}))
    assert (qualified.source_type, qualified.tier, qualified.reliability, qualified.in_catalog) == (
        "official",
        1,
        "high",
        True,
    )


def test_explicit_metadata_is_kept_and_outside_catalog_requires_it():
    explicit = qualify(
        SourceIn.model_validate(
            {**BASE, "url": "https://demagog.org.pl/x", "sourceType": "secondary", "tier": 3, "reliability": "low"}
        )
    )
    assert (explicit.source_type, explicit.tier) == ("secondary", 3)
    outside = qualify(
        SourceIn.model_validate(
            {**BASE, "url": "https://example.org/a", "sourceType": "secondary", "tier": 3, "reliability": "low"}
        )
    )
    assert outside.in_catalog is False
    with pytest.raises(SourceOutsideCatalogError):
        qualify(SourceIn.model_validate({**BASE, "url": "https://example.org/a"}))
