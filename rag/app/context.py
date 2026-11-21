import logging
import re
from xml.sax.saxutils import escape, quoteattr

from app.models import Evidence

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = re.compile(
    r"ignore (all |the )?(previous|above) instructions"
    r"|disregard (all |the )?(previous|above)"
    r"|system prompt"
    r"|you are now"
    r"|zignoruj (wszystkie |poprzednie |powyższe )*(instrukcje|polecenia)"
    r"|nie stosuj się do (poprzednich |powyższych )?(instrukcji|poleceń)"
    r"|prompt systemowy"
    r"|jesteś teraz",
    re.IGNORECASE,
)


def contains_instructions(text: str) -> bool:
    """Heuristic flag for prompt-injection attempts inside source text; the text itself is still passed as data."""
    return INJECTION_PATTERNS.search(text) is not None


def build_context_xml(evidence: list[Evidence]) -> str:
    """Renders evidence as an escaped <dostepne_zrodla> block so source text cannot close or forge tags."""
    blocks = []
    for item in evidence:
        attributes = " ".join(
            f"{name}={quoteattr(str(value))}"
            for name, value in (
                ("id", item.chunk_id),
                ("tier", item.tier),
                ("wiarygodnosc", item.reliability),
                ("typ", item.source.source_type),
                ("tytul", item.source.title),
                ("wydawca", item.source.publisher),
                ("data_publikacji", item.source.published_at.isoformat()),
                ("data_pobrania", item.source.retrieved_at.isoformat()),
                ("link", item.source.url),
                ("podejrzana_tresc", "tak" if item.suspicious_instructions else "nie"),
            )
        )
        blocks.append(f"<zrodlo {attributes}>\n{escape(item.text)}\n</zrodlo>")
    return "<dostepne_zrodla>\n" + "\n".join(blocks) + "\n</dostepne_zrodla>"
