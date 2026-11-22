import re
from functools import lru_cache

from app.config import settings
from app.languages import LanguageProfile, load_profile

WORD = re.compile(r"[^\W_]+")


@lru_cache(maxsize=1)
def _profile() -> LanguageProfile:
    return load_profile(settings.corpus_language)


def content_words(text: str) -> list[str]:
    """Lower-cased words without stopwords, in their original inflected form, in order of appearance."""
    stopwords = _profile().stopwords
    return [word for word in WORD.findall(text.lower()) if word not in stopwords]


def lexical_tokens(text: str) -> list[str]:
    """
    Content words cut to a stem by the language profile. PostgreSQL has no Polish text search configuration (Supabase
    ships only `simple`), so stemming happens here and the database indexes the result as is.
    """
    stemmer = _profile().stemmer
    return [stemmer.stem_word(word) for word in content_words(text)]
