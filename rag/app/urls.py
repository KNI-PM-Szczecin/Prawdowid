from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that only track the visitor; two addresses differing by them point at the same page.
TRACKING_PARAMETER_PREFIXES = ("utm_",)
TRACKING_PARAMETERS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src"}
WWW_PREFIX = "www."
MOBILE_PREFIX = "m."


def normalize_url(url: str) -> str:
    """
    Canonical form for comparing two addresses of the same page: https, lowercase host without `www.` or `m.`,
    no fragment, no tracking parameters, sorted query, no trailing slash. Never used for fetching.
    """
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    for prefix in (WWW_PREFIX, MOBILE_PREFIX):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith(TRACKING_PARAMETER_PREFIXES)
    )
    path = parts.path.rstrip("/")
    return urlunsplit(("https", host, path, urlencode(query), ""))
