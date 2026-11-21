import json
from dataclasses import dataclass
from pathlib import Path

PROFILES_DIR = Path(__file__).parent


class SuffixStemmer:
    """Light, dictionary-free stemmer: strips the longest known inflection suffix while keeping a minimum stem."""

    def __init__(self, suffixes: list[str], min_stem_length: int) -> None:
        self._suffixes = sorted(suffixes, key=len, reverse=True)
        self._min_stem_length = min_stem_length

    def stem_word(self, word: str) -> str:
        for suffix in self._suffixes:
            if word.endswith(suffix) and len(word) - len(suffix) >= self._min_stem_length:
                return word[: -len(suffix)]
        return word


@dataclass(frozen=True)
class LanguageProfile:
    stemmer: SuffixStemmer
    stopwords: set[str]


def load_profile(language_code: str) -> LanguageProfile:
    """Loads languages/<code>.json; adding a language means adding one data file."""
    profile_path = PROFILES_DIR / f"{language_code}.json"
    if not profile_path.is_file():
        raise ValueError(f"No language profile for '{language_code}' in {PROFILES_DIR}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return LanguageProfile(
        stemmer=SuffixStemmer(profile["suffixes"], profile["min_stem_length"]),
        stopwords=set(profile["stopwords"]),
    )
