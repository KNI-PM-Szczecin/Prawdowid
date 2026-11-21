import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from app.models import CatalogEntry, QualifiedSource, SourceCatalog, SourceIn

CATALOG_PATH = Path(__file__).parent / "data" / "sources_catalog.json"
QUALIFICATION_FIELDS = ("source_type", "tier", "reliability")
OUTSIDE_CATALOG_MESSAGE = (
    "Domena {domain} nie jest w katalogu źródeł. Dla źródła spoza katalogu podaj jawnie sourceType, tier i reliability."
)


class SourceOutsideCatalogError(ValueError):
    """Document from an unknown domain was sent without explicit qualification metadata."""


@lru_cache(maxsize=1)
def load_catalog() -> SourceCatalog:
    return SourceCatalog.model_validate(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


def domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def resolve_entry(url: str) -> CatalogEntry | None:
    """Longest matching domain wins, so a specific entry (isap.sejm.gov.pl) beats a broad one (gov.pl)."""
    host = domain_of(url)
    best: tuple[int, CatalogEntry] | None = None
    for entry in load_catalog().entries:
        for domain in entry.domains:
            if (host == domain or host.endswith("." + domain)) and (best is None or len(domain) > best[0]):
                best = (len(domain), entry)
    return best[1] if best else None


def qualify(source: SourceIn) -> QualifiedSource:
    """
    Fills sourceType, tier and reliability from the catalog entry matching the URL's domain.
    Outside the catalog all three must be given explicitly; the document is then audited as outside the catalog.
    """
    entry = resolve_entry(str(source.url))
    values = source.model_dump()
    for field in QUALIFICATION_FIELDS:
        if values[field] is None and entry is not None:
            values[field] = getattr(entry, field)
    try:
        return QualifiedSource.model_validate({**values, "in_catalog": entry is not None})
    except ValidationError as error:
        raise SourceOutsideCatalogError(OUTSIDE_CATALOG_MESSAGE.format(domain=domain_of(str(source.url)))) from error
