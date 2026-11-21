import re
from xml.sax.saxutils import escape, quoteattr

from app.models import Passage

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


def build_context_xml(passages: list[Passage]) -> str:
    """Renders passages as an escaped <dostepne_zrodla> block so source text cannot close or forge tags."""
    blocks = []
    for item in passages:
        attributes = " ".join(
            f"{name}={quoteattr(str(value))}"
            for name, value in (
                ("id", item.chunk_id),
                ("document_id", item.document_id),
                ("tier", item.tier),
                ("reliability", item.reliability),
                ("source_type", item.source_type),
                ("title", item.title),
                ("publisher", item.publisher),
                ("published_at", item.published_at.isoformat() if item.published_at else "unknown"),
                ("fetched_at", item.fetched_at.isoformat()),
                ("url", item.url),
                ("flags", ",".join(item.flags)),
            )
        )
        blocks.append(f"<zrodlo {attributes}>\n{escape(item.passage)}\n</zrodlo>")
    return "<dostepne_zrodla>\n" + "\n".join(blocks) + "\n</dostepne_zrodla>"
