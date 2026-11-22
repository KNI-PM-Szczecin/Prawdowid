import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.lexical import stem_word

COUNTRIES_PATH = Path(__file__).parent / "data" / "countries.json"
WORD = re.compile(r"[^\W_]+")
ALIAS = re.compile(r"\(([^)]*)\)")
POLISH_LETTERS_WITHOUT_DECOMPOSITION = str.maketrans({"ł": "l", "Ł": "L"})
# Polish locatives change the last consonant of the stem (Włochy -> we Włoszech, Malta -> na Malcie, Egipt -> w
# Egipcie). Folding both sides the same way keeps the nominative stem visible in the inflected form.
STEM_ALTERNATIONS = (("sz", "ch"), ("ci", "t"))
# What may follow a country's stem in an inflected form (folded, without diacritics); anything longer is another
# word that happens to start the same way (Malta / maltretowanie, Mali / malina).
INFLECTION_ENDINGS = frozenset(
    {
        "",
        "a",
        "e",
        "i",
        "o",
        "u",
        "y",
        "ia",
        "ie",
        "ii",
        "io",
        "iu",
        "ji",
        "em",
        "om",
        "ow",
        "ej",
        "ym",
        "ach",
        "ami",
        "ech",
        "zech",
        "owi",
        "ego",
        "emu",
        "ych",
        "ymi",
        "iej",
        "iach",
        "iami",
        "owa",
        "owe",
        "owy",
        "owej",
        "owym",
        "owych",
        "owego",
    }
)
# Connectors inside multi-word names ("Bośnia i Hercegowina", "Tristan da Cunha") carry no country.
MIN_NAME_TOKEN_CHARS = 3


@dataclass(frozen=True)
class Country:
    iso: str
    name: str


@dataclass(frozen=True)
class _CountryPattern:
    country: Country
    stems: tuple[str, ...]
    name_tokens: tuple[str, ...]
    aliases: frozenset[str]


@dataclass(frozen=True)
class CountryMention:
    country: Country
    # Folded claim words that matched, mapped to the nominative token of the name they stand for.
    nominatives: dict[str, str]


def fold(word: str) -> str:
    """Lower case without diacritics and with the locative consonant alternations undone, for comparison only."""
    decomposed = unicodedata.normalize("NFKD", word.casefold().translate(POLISH_LETTERS_WITHOUT_DECOMPOSITION))
    folded = "".join(character for character in decomposed if not unicodedata.combining(character))
    for written, stem_form in STEM_ALTERNATIONS:
        folded = folded.replace(written, stem_form)
    return folded


def _inflection_of(stem: str, folded_word: str) -> bool:
    return folded_word.startswith(stem) and folded_word[len(stem) :] in INFLECTION_ENDINGS


@lru_cache(maxsize=1)
def load_countries() -> tuple[Country, ...]:
    payload = json.loads(COUNTRIES_PATH.read_text(encoding="utf-8"))
    return tuple(Country(iso=item["iso"], name=item["name"]) for item in payload["countries"])


@lru_cache(maxsize=1)
def _patterns() -> tuple[_CountryPattern, ...]:
    patterns = []
    for country in load_countries():
        aliases = frozenset(fold(alias) for group in ALIAS.findall(country.name) for alias in WORD.findall(group))
        tokens = tuple(
            token for token in WORD.findall(ALIAS.sub(" ", country.name)) if len(token) >= MIN_NAME_TOKEN_CHARS
        )
        if tokens:
            patterns.append(
                _CountryPattern(
                    country=country,
                    stems=tuple(stem_word(fold(token)) for token in tokens),
                    name_tokens=tokens,
                    aliases=aliases,
                )
            )
    return tuple(patterns)


def _candidate_words(text: str) -> list[str]:
    """
    Words that may name a country. In a normally written sentence only capitalised words do: lowercase "czad" (carbon
    monoxide) or "kuba" are ordinary words. Text written entirely in lower case gives no such hint, so all words count.
    """
    words = WORD.findall(text)
    if text == text.lower():
        return words
    return [word for word in words if word[:1].isupper()]


def country_mentions(text: str) -> list[CountryMention]:
    """
    Countries named in the text, also in inflected forms (we Włoszech, z Francji, w Stanach Zjednoczonych). A name
    of several words needs all of them; a shorter name contained in a longer matched one (Sudan in Sudan Południowy)
    is dropped.
    """
    folded_words = list(dict.fromkeys(fold(word) for word in _candidate_words(text)))
    mentions: list[CountryMention] = []
    for pattern in _patterns():
        alias = next((word for word in folded_words if word in pattern.aliases), None)
        if alias is not None:
            mentions.append(CountryMention(pattern.country, {alias: alias.upper()}))
            continue
        nominatives: dict[str, str] = {}
        for stem, name_token in zip(pattern.stems, pattern.name_tokens, strict=True):
            word = next((word for word in folded_words if _inflection_of(stem, word)), None)
            if word is None:
                break
            nominatives[word] = name_token
        else:
            mentions.append(CountryMention(pattern.country, nominatives))
    return [
        mention
        for mention in mentions
        if not any(other is not mention and mention.nominatives.keys() < other.nominatives.keys() for other in mentions)
    ]


def nominative_forms(text: str) -> dict[str, str]:
    """Lower-cased words of the text that name a country, mapped to that word of the name in the nominative."""
    folded_to_nominative = {
        folded: nominative for mention in country_mentions(text) for folded, nominative in mention.nominatives.items()
    }
    return {
        word.lower(): folded_to_nominative[fold(word)]
        for word in WORD.findall(text)
        if fold(word) in folded_to_nominative
    }
