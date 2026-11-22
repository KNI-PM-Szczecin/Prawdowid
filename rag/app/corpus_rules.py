import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

RULES_PATH = Path(__file__).parent / "data" / "corpus_rules.json"


@dataclass(frozen=True)
class CorpusRules:
    hosts: frozenset[str]
    url_patterns: tuple[re.Pattern[str], ...]
    title_patterns: tuple[re.Pattern[str], ...]


@lru_cache(maxsize=1)
def load_rules() -> CorpusRules:
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return CorpusRules(
        hosts=frozenset(host.lower() for host in payload["excludeHosts"]),
        url_patterns=tuple(re.compile(pattern, re.IGNORECASE) for pattern in payload["excludeUrlPatterns"]),
        title_patterns=tuple(re.compile(pattern, re.IGNORECASE) for pattern in payload["excludeTitlePatterns"]),
    )


def _is_host_in(host: str, hosts: frozenset[str]) -> bool:
    return any(host == candidate or host.endswith("." + candidate) for candidate in hosts)


def exclusion_reason(url: str, title: str, exempt_hosts: frozenset[str] = frozenset()) -> str | None:
    """
    Why a page stays out of the evidence corpus (host, address or title rule), or None when it may be indexed.
    `exempt_hosts` lifts the host rule only (feeds of excluded hosts, see feeds.json); address and title rules stay.
    """
    rules = load_rules()
    host = (urlparse(url).hostname or "").lower()
    if _is_host_in(host, rules.hosts) and not _is_host_in(host, exempt_hosts):
        return f"host {host} excluded"
    for pattern in rules.url_patterns:
        if pattern.search(url):
            return f"url matches {pattern.pattern}"
    normalized_title = " ".join(title.split())
    for pattern in rules.title_patterns:
        if pattern.search(normalized_title):
            return f"title matches {pattern.pattern}"
    return None
