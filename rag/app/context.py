import re
import unicodedata
from xml.sax.saxutils import escape, quoteattr

from app.models import Passage

INVISIBLE_CHARACTERS = re.compile("[­​-‏⁠-⁤﻿]")
WHITESPACE = re.compile(r"\s+")
POLISH_LETTERS_WITHOUT_DECOMPOSITION = str.maketrans({"ł": "l"})

# Patterns run on normalized text: lowercase, no diacritics, single spaces.
_EARLIER = r"(?:previous|prior|above|earlier|preceding|original|system|all|any|your|these|those)"
_RULES = r"(?:instructions?|rules|prompts?|directions|guidelines|messages|context)"
_PL_EARLIER = (
    r"(?:wszystkie|wszystkich|wszelkie|poprzednie|poprzednich|powyzsze|powyzszych|wczesniejsze|"
    r"wczesniejszych|dotychczasowe|dotychczasowych|swoje|swoich|twoje|twoich|systemowe|systemowych|o)"
)
_PL_RULES = (
    r"(?:instrukcje|instrukcji|instrukcjach|polecenia|polecen|poleceniach|zasady|zasad|zasadach|"
    r"reguly|regul|regulach|wytyczne|wytycznych|prompt)"
)

INJECTION_PATTERNS = re.compile(
    "|".join(
        (
            rf"\b(?:ignore|disregard|forget|override|bypass)\s+(?:(?:the|all|any|your|of)\s+)*{_EARLIER}\s+{_RULES}",
            r"\bnew\s+(?:task|instructions?|role|objective|system\s+prompt)\s*:",
            r"\byou\s+are\s+now\b",
            r"\bfrom\s+now\s+on,?\s+you\b",
            r"\b(?:act\s+as|pretend\s+(?:to\s+be|you\s+are)|roleplay\s+as)\s+(?:an?|the|my)\b",
            r"\bsystem\s+(?:prompt|message)\b",
            r"\bdeveloper\s+(?:mode|message)\b",
            r"\bjailbreak",
            r"\b(?:reveal|print|show|repeat)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)",
            r"\b(?:classify|rate|mark|label)\s+(?:this|the|it)(?:\s+claim)?\s+as\s+(?:true|verified|confirmed|false)",
            r"\b(?:respond|answer|reply|output)\s+only\s+with\b",
            r"<\s*/?\s*(?:system|instructions?|assistant|im_start|im_end)\s*>",
            r"<\|im_(?:start|end)\|>",
            r"\[/?inst\]",
            r"#{2,}\s*(?:instruction|system)",
            rf"\b(?:zignoruj|pomin|zapomnij\s+o|olej|nie\s+stosuj\s+sie\s+do|nie\s+bierz\s+pod\s+uwage)\s+"
            rf"(?:{_PL_EARLIER}\s+)*{_PL_RULES}",
            r"\bnowe\s+(?:zadanie|polecenie|instrukcje|instrukcja)\s*:",
            r"\b(?:od\s+teraz|odtad)\s+(?:jestes|bedziesz|masz)\b",
            r"\bjestes\s+teraz\b",
            r"\budawaj,?\s+ze\b",
            r"\bwciel\s+sie\s+w\b",
            r"\b(?:prompt|komunikat)\s+systemowy\b",
            r"\binstrukcje\s+systemowe\b",
            r"\btryb\s+(?:dewelopera|developera)\b",
            r"\b(?:ujawnij|pokaz|wypisz|powtorz)\s+(?:swoj|swoje|twoj|twoje)\s+(?:prompt|instrukcje|polecenia)",
            r"\b(?:ocen|oznacz|uznaj|zaklasyfikuj|oceniaj)\s+(?:to|ten|te|ta|je|go)?\s*\w*\s*(?:jako|za)\s+"
            r"(?:prawdziw|potwierdzon|wiarygodn|falszyw)",
            r"\b(?:odpowiedz|odpowiadaj)\s+(?:tylko|wylacznie)\b",
        )
    )
)


def normalize_for_detection(text: str) -> str:
    """Strips invisible characters, case and diacritics so obfuscated variants hit the same patterns."""
    visible = INVISIBLE_CHARACTERS.sub("", unicodedata.normalize("NFKC", text))
    decomposed = unicodedata.normalize("NFKD", visible.casefold().translate(POLISH_LETTERS_WITHOUT_DECOMPOSITION))
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return WHITESPACE.sub(" ", without_marks)


def contains_instructions(text: str) -> bool:
    """Heuristic flag for prompt-injection attempts inside source text; the text itself is still passed as data."""
    return INJECTION_PATTERNS.search(normalize_for_detection(text)) is not None


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
