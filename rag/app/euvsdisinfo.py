import asyncio
import html
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from app.config import settings
from app.embeddings import EmbeddingModels
from app.incidents import index_incidents
from app.models import IncidentIn
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

SOURCE_NAME = "euvsdisinfo"
CASES_TOOL = "cases"
JSONRPC_VERSION = "2.0"
# Required by the server: both types, otherwise 406 (EUvsDisinfo MCP docs, error codes).
ACCEPT_HEADER = "application/json, text/event-stream"
SSE_DATA_PREFIX = "data:"
HTML_TAG = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")
LICENSE_NOTE = "EUvsDisinfo (EEAS East StratCom Task Force), euvsdisinfo.eu"


class EuvsDisinfoError(Exception):
    """Transport, auth or protocol failure talking to the EUvsDisinfo MCP server."""


@dataclass(frozen=True)
class CasesPage:
    total: int
    incidents: list[IncidentIn]
    skipped: int


def _plain_text(raw: str | None) -> str:
    return WHITESPACE.sub(" ", html.unescape(HTML_TAG.sub(" ", raw or ""))).strip()


def parse_case(case: dict) -> IncidentIn | None:
    """Maps one `cases` record to the catalog format; records without id, claim or URL are skipped."""
    claim = _plain_text(case.get("claim"))
    title = _plain_text(case.get("title")) or claim[: settings.incident_summary_max_chars]
    timestamp = case.get("date")
    disinformation_links = [link for link in case.get("linksToDisinformation") or [] if isinstance(link, dict)]
    languages = sorted(
        {
            link["language"]["name"]
            for link in disinformation_links
            if isinstance(link.get("language"), dict) and link["language"].get("name")
        }
    )
    links = [link["url"] for link in disinformation_links if isinstance(link.get("url"), str) and link["url"]]
    try:
        return IncidentIn(
            incident_id=str(case["id"]),
            source=SOURCE_NAME,
            title=title,
            summary=claim,
            url=case["url"],
            published_at=datetime.fromtimestamp(timestamp, tz=UTC) if isinstance(timestamp, int | float) else None,
            countries=[country["title"] for country in case.get("countries") or [] if country.get("title")],
            languages=languages,
            license=LICENSE_NOTE,
            links=links,
        )
    except (KeyError, ValidationError):
        return None


def _jsonrpc_payload(response: httpx.Response) -> dict:
    """The server answers either plain JSON or a single SSE `message` event carrying the JSON-RPC response."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        events = [
            line[len(SSE_DATA_PREFIX) :].strip()
            for line in response.text.splitlines()
            if line.startswith(SSE_DATA_PREFIX)
        ]
        if not events:
            raise EuvsDisinfoError("Empty event stream from EUvsDisinfo")
        return json.loads(events[-1])
    return response.json()


class EuvsDisinfoClient:
    """MCP client in stateless mode: every tools/call is a single POST with a client-generated session id."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(timeout=settings.euvsdisinfo_timeout_seconds, transport=transport)

    @property
    def enabled(self) -> bool:
        return bool(settings.euvsdisinfo_token)

    async def fetch_cases(self, limit: int, offset: int) -> CasesPage:
        try:
            response = await self._client.post(
                settings.euvsdisinfo_url,
                headers={
                    "Authorization": f"Bearer {settings.euvsdisinfo_token}",
                    "Accept": ACCEPT_HEADER,
                    "mcp-session-id": str(uuid.uuid4()),
                },
                json={
                    "jsonrpc": JSONRPC_VERSION,
                    "id": offset,
                    "method": "tools/call",
                    "params": {"name": CASES_TOOL, "arguments": {"limit": limit, "offset": offset}},
                },
            )
            response.raise_for_status()
            payload = _jsonrpc_payload(response)
        except httpx.HTTPStatusError as error:
            raise EuvsDisinfoError(f"EUvsDisinfo returned HTTP {error.response.status_code}") from error
        except (httpx.HTTPError, ValueError) as error:
            raise EuvsDisinfoError(f"EUvsDisinfo request failed: {type(error).__name__}") from error
        if "error" in payload:
            raise EuvsDisinfoError(f"EUvsDisinfo JSON-RPC error {payload['error'].get('code')}")
        structured = (payload.get("result") or {}).get("structuredContent") or {}
        raw_cases = structured.get("cases")
        if not isinstance(raw_cases, list):
            raise EuvsDisinfoError("EUvsDisinfo response has no structuredContent.cases")
        parsed = [parse_case(case) for case in raw_cases]
        incidents = [incident for incident in parsed if incident is not None]
        return CasesPage(
            total=int(structured.get("total", 0)), incidents=incidents, skipped=len(parsed) - len(incidents)
        )

    async def close(self) -> None:
        await self._client.aclose()


@dataclass
class SyncState:
    running: bool = False
    last_finished_at: datetime | None = None
    last_indexed: int = 0
    last_skipped: int = 0
    last_error: str | None = None
    available: int | None = None


sync_state = SyncState()
_sync_lock = asyncio.Lock()


async def sync_cases(
    client: EuvsDisinfoClient, models: EmbeddingModels, incidents: VectorStore, max_cases: int
) -> SyncState:
    """
    Imports the newest `max_cases` EUvsDisinfo cases into the incident catalog, page by page.
    Idempotent (same case = same point id). A second call while one runs is refused, a failure keeps what was
    already indexed and is recorded in `sync_state.last_error`.
    """
    if _sync_lock.locked():
        logger.warning("EUvsDisinfo sync already running, request ignored")
        return sync_state
    async with _sync_lock:
        sync_state.running = True
        sync_state.last_error = None
        indexed = skipped = 0
        try:
            offset = 0
            while offset < max_cases:
                requested = min(settings.euvsdisinfo_page_size, max_cases - offset)
                page = await client.fetch_cases(requested, offset)
                sync_state.available = page.total
                if page.incidents:
                    indexed += await index_incidents(page.incidents, models, incidents)
                skipped += page.skipped
                # Advance by what actually arrived: a server-side page-size cap smaller than the request would
                # otherwise silently skip the difference on every further page.
                fetched = len(page.incidents) + page.skipped
                offset += fetched
                logger.info(
                    "EUvsDisinfo sync: %d indexed, %d skipped, offset %d of %d", indexed, skipped, offset, page.total
                )
                # A short page is the end of the list even when the server reports no total.
                if fetched < requested or (page.total and offset >= page.total):
                    break
        except EuvsDisinfoError as error:
            sync_state.last_error = str(error)
            logger.error("EUvsDisinfo sync stopped: %s", error)
        finally:
            sync_state.running = False
            sync_state.last_finished_at = datetime.now(UTC)
            sync_state.last_indexed = indexed
            sync_state.last_skipped = skipped
    return sync_state
