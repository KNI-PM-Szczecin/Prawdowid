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
            # Phrasings from the external deepset/prompt-injections set that the rules above missed.
            r"\bforget\s+(?:about\s+)?(?:everything|all|anything)\b",
            r"\bignore\s+(?:the\s+)?(?:above|everything|anything|all|what)\b",
            r"\b(?:ignore|disregard|forget|ignoring|disregarding)\s+(?:all\s+)?(?:the\s+)?(?:provided\s+|given\s+)?"
            r"(?:context|articles?|sources?|documents?)\b",
            r"\b(?:not\s+by|not\s+from|not\s+according\s+to)\s+the\s+(?:provided\s+)?(?:articles?|documents?|sources?|context)\b",
            r"\banswer\s+(?:by|from|with)\s+your\s+own\s+knowledge\b",
            r"\b(?:now|here)\s+(?:comes?|is|are)\s+(?:a|the|your|some)?\s*(?:great\s+)?(?:new|next|second|further)\s+"
            r"(?:tasks?|assignments?|challenge|test|job|orders?)\b",
            r"\b(?:new|additional|further)\s+(?:instructions?|orders?|tasks?)\s+(?:follow|are\s+followed|for\s+you)\b",
            r"\byour\s+(?:new\s+)?(?:instructions?|task|job)\s+(?:is|are)\s+(?:now\s+)?to\b",
            r"\b(?:concentrate|focus)\s+(?:only\s+)?on\s+(?:this|the\s+(?:next|following|new))\s+(?:task|assignment)\b",
            r"\b(?:you\s+are|you're)\s+(?:not\s+)?supposed\s+to\b",
            r"\b(?:don't|do\s+not|never)\s+(?:listen\s+to|follow|pay\s+attention\s+to|look\s+(?:in|at))\s+(?:anything|what|the)\b",
            r"\b(?:just|only)\s+(?:output|print|say|write|reply|respond)\s*:?\s*\"",
            r"\b(?:now|okay|ok)[,.!]?\s+you\s+are\s+(?:a|an|the|my)?\s*\w+",
            r"\byou\s+(?:now\s+)?act\s+as\b",
            r"\b(?:imagine|suppose)\s+(?:that\s+)?you\s+are\b",
            r"\byou\s+are\s+role-?\s*playing\b",
            r"\brepeat\s+after\s+me\b",
            r"\b(?:above|previous|initial|original)\s+prompt\b",
            r"\bwhat\s+(?:is|was)\s+written\s+(?:above|before|at\s+the\s+beginning)\b",
            r"\b(?:instructions?|orders?|commands?)\s*:\s*\w",
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
            r"\bzapomnij\s+(?:o\s+)?(?:wszystkim|wszystko|wszystkich)\b",
            r"\bzignoruj\s+(?:to,?\s+)?co\s+(?:bylo\s+)?(?:powyzej|wyzej|wczesniej|przed)",
            r"\b(?:zignoruj|pomin|pomijajac|ignorujac)\s+(?:wszystkie\s+|dostepne\s+|podane\s+)?"
            r"(?:artykuly|zrodla|dokumenty|kontekst)\b",
            r"\bnie\s+(?:sluchaj|stosuj\s+sie\s+do|zwracaj\s+uwagi\s+na)\s+(?:tego,?\s+)?co\s+(?:bylo\s+)?"
            r"(?:powyzej|wyzej|wczesniej|napisano|napisalem)",
            r"\b(?:teraz|oto|a\s+teraz)\s+(?:nowe|kolejne|twoje\s+nowe)\s+(?:zadanie|polecenie|wyzwanie)\b",
            r"\b(?:nowe|dodatkowe|kolejne)\s+(?:instrukcje|polecenia)\s+(?:dla\s+ciebie|brzmia|sa\s+nastepujace)\b",
            r"\btwoje\s+(?:nowe\s+)?(?:instrukcje|zadanie|polecenie)\s+(?:to|brzmi)\b",
            r"\b(?:skup|skoncentruj)\s+sie\s+(?:tylko\s+|wylacznie\s+)?na\s+(?:tym|nowym|nastepnym|kolejnym)\s+zadaniu\b",
            r"\b(?:nie\s+wolno|nie\s+mozesz|masz)\s+(?:ci\s+)?(?:mowic|powiedziec|odpowiadac)\b",
            r"\bodpowiadaj\s+(?:zawsze|na\s+kazde\s+pytanie)\b",
            r"\bodpowiadaj\s+(?:z\s+)?wlasn(?:a|ej)\s+wiedz",
            r"\bwyobraz\s+sobie,?\s+ze\s+jestes\b",
            r"\bpowtarzaj\s+za\s+mna\b",
            r"\b(?:napisz|powiedz|wypisz)\s+tylko\s*:?\s*\"",
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
