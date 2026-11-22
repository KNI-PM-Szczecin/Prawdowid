import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app import db
from app.config import settings
from app.corpus_sync import CorpusSyncState, Page, run_corpus_job, to_document
from app.countries import Country, country_mentions
from app.embeddings import EmbeddingModels
from app.ingest import DuplicateDocumentError, content_hash, delete_document_chunks, ingest_document
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

DOCUMENT_PREFIX = "odyseusz:"
COUNTRY_LIST_PATH = "profile-panstw/mini"
PROFILE_PATH = "profile-panstw/{iso}"
WARNINGS_PATH = "{iso}/ostrzezenia"
ISO_CODE = re.compile(r"^[A-Z]{2}$")
# Notices use Markdown links; the address stays visible next to its label so the citizen can follow it.
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
TITLE_TEMPLATE = "Odyseusz (MSZ): {name} - informacje dla podróżujących"
# The notice text never names its country, so every document starts with the name and the date.
LEAD_TEMPLATE = "{name} (komunikat MSZ dla podróżujących, aktualizacja {updated}):"
WARNING_TEMPLATE = "Poziom ostrzeżenia MSZ dla podróżujących ({name}, obowiązuje od {since}): {text}"

odyseusz_state = CorpusSyncState()
_refresh_lock = asyncio.Lock()


class OdyseuszError(Exception):
    """The Odyseusz API did not answer with a usable JSON document."""


@dataclass
class OdyseuszFillResult:
    status: str
    indexed: int = 0


def odyseusz_document_id(iso: str) -> str:
    return f"{DOCUMENT_PREFIX}{iso}"


def country_page_url(iso: str) -> str:
    """The page a citizen opens for a country on odyseusz.gov.pl (the SPA routes a bare ISO code to the profile)."""
    return f"{settings.odyseusz_site.rstrip('/')}/{iso}"


def strip_markdown_links(text: str) -> str:
    return MARKDOWN_LINK.sub(r"\1 (\2)", text)


def _as_paragraphs(text: str) -> str:
    """Every line of the notice becomes its own paragraph, so chunking keeps list items and sentences whole."""
    return "\n\n".join(line.strip() for line in strip_markdown_links(text).splitlines() if line.strip())


def parse_country_list(payload: object) -> list[Country]:
    """Countries from /profile-panstw/mini; entries without a two-letter ISO code or a name are skipped."""
    if not isinstance(payload, list):
        raise OdyseuszError("country list is not a JSON array")
    countries: list[Country] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        iso, name = str(item.get("kodIso") or "").upper(), str(item.get("nazwa") or "").strip()
        if ISO_CODE.match(iso) and name:
            countries.append(Country(iso=iso, name=name))
    return countries


def _parse_date(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _warning_paragraph(name: str, warning: dict | None) -> str | None:
    text = str((warning or {}).get("trescOstrzezeniaDlaKraju") or "").strip()
    if not text:
        return None
    since = str((warning or {}).get("dataObowiazywaniaOd") or "").strip() or "brak daty"
    return WARNING_TEMPLATE.format(name=name, since=since, text=" ".join(_as_paragraphs(text).split("\n\n")))


def build_page(iso: str, profile: dict, warning: dict | None, fetched_at: datetime) -> Page | None:
    """
    One document per country with a current notice: the country name and update date first, then the notice, then
    the warning level when the API gave one. No notice (or no update date, which evidence needs) means no document.
    """
    notice = str(profile.get("trescPowiadomieniaDluga") or "").strip()
    name = str(profile.get("nazwa") or "").strip()
    updated_raw = str(profile.get("dataAktualizacji") or "").strip()
    published_at = _parse_date(updated_raw)
    if not notice or not name or published_at is None:
        return None
    paragraphs = [f"{LEAD_TEMPLATE.format(name=name, updated=updated_raw)}\n\n{_as_paragraphs(notice)}"]
    if (warning_text := _warning_paragraph(name, warning)) is not None:
        paragraphs.append(warning_text)
    return Page(
        document_id=odyseusz_document_id(iso),
        url=country_page_url(iso),
        title=TITLE_TEMPLATE.format(name=name),
        content="\n\n".join(paragraphs),
        fetched_at=fetched_at,
        published_at=published_at,
    )


async def _get_json(client: httpx.AsyncClient, path: str) -> object:
    url = f"{settings.odyseusz_api_url.rstrip('/')}/{path}"
    try:
        response = await client.get(
            url, headers={"User-Agent": settings.corpus_fetch_user_agent, "Accept": "application/json"}
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise OdyseuszError(f"{path}: {type(error).__name__}") from error
    if len(response.content) > settings.odyseusz_max_bytes:
        raise OdyseuszError(f"{path}: larger than {settings.odyseusz_max_bytes} bytes")
    try:
        return response.json()
    except ValueError as error:
        raise OdyseuszError(f"{path}: not JSON") from error


async def fetch_country_page(client: httpx.AsyncClient, iso: str, fetched_at: datetime) -> Page | None:
    """
    The country's notice as a page, or None when it has none. The warning level is optional: when its request
    fails the notice is still indexed without it. Raises OdyseuszError when the profile itself is unavailable.
    """
    if not ISO_CODE.match(iso):
        raise OdyseuszError(f"invalid country code {iso!r}")
    profile = await _get_json(client, PROFILE_PATH.format(iso=iso))
    if not isinstance(profile, dict):
        raise OdyseuszError(f"profile {iso} is not a JSON object")
    if not str(profile.get("trescPowiadomieniaDluga") or "").strip():
        return None
    warning: dict | None = None
    try:
        payload = await _get_json(client, WARNINGS_PATH.format(iso=iso))
        warning = payload if isinstance(payload, dict) else None
    except OdyseuszError as error:
        logger.warning("Odyseusz: warning level of %s unavailable (%s), notice indexed without it", iso, error)
    page = build_page(iso, profile, warning, fetched_at)
    if page is None:
        raise OdyseuszError(f"profile {iso} has a notice but no country name or update date")
    return page


async def _unchanged(page: Page) -> bool:
    return await db.document_content_hash(page.document_id) == content_hash(page.content)


async def refresh_odyseusz(
    models: EmbeddingModels, store: VectorStore, transport: httpx.AsyncBaseTransport | None = None
) -> CorpusSyncState:
    """
    Imports the current MSZ notice of every country from the Odyseusz API through the normal ingest path. A changed
    notice replaces the country's document, an unchanged one is not embedded again, and a notice MSZ has withdrawn
    removes the document, so the corpus never shows an expired notice as current. One failing country never stops
    the run; a failing country list ends it with last_error set.
    """

    async def load_pages(state: CorpusSyncState) -> list[Page]:
        pages: list[Page] = []
        async with httpx.AsyncClient(
            timeout=settings.odyseusz_timeout_seconds, follow_redirects=False, transport=transport
        ) as client:
            countries = parse_country_list(await _get_json(client, COUNTRY_LIST_PATH))
            for country in countries:
                await asyncio.sleep(settings.odyseusz_request_delay_seconds)
                try:
                    page = await fetch_country_page(client, country.iso, datetime.now(UTC))
                except OdyseuszError as error:
                    state.failed += 1
                    logger.warning("Odyseusz: %s skipped (%s)", country.iso, error)
                    continue
                if page is None:
                    removed = await delete_document_chunks(odyseusz_document_id(country.iso), store)
                    if removed:
                        logger.info("Odyseusz: notice for %s withdrawn, document removed", country.iso)
                    continue
                if await _unchanged(page):
                    state.already_present += 1
                    continue
                pages.append(page)
        return pages

    return await run_corpus_job(
        odyseusz_state,
        _refresh_lock,
        "Odyseusz refresh",
        load_pages,
        models,
        store,
        strip_boilerplate=False,
        allow_near_duplicate=True,
    )


class OdyseuszClient:
    """
    On-demand part of the importer: when a claim names a country, that country's notice is fetched inside the
    search request and indexed, so the same request can cite it. Only the ISO code leaves the system, to an MSZ
    service. It also runs while the scheduled refresh is going: a full refresh takes minutes (embedding on CPU), and
    a question asked meanwhile must not lose its source. Whichever path comes second sees the same content hash and
    skips the embedding.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.odyseusz_timeout_seconds, follow_redirects=False, transport=transport
        )
        self._background: set[asyncio.Task] = set()

    @property
    def enabled(self) -> bool:
        return settings.odyseusz_enabled

    async def _stored_recently(self, document_id: str, now: datetime) -> bool:
        fetched_at = await db.document_fetched_at(document_id)
        return fetched_at is not None and now - fetched_at < timedelta(
            minutes=settings.odyseusz_refresh_interval_minutes
        )

    async def _index_country(self, country: Country, models: EmbeddingModels, store: VectorStore) -> int:
        now = datetime.now(UTC)
        if await self._stored_recently(odyseusz_document_id(country.iso), now):
            return 0
        page = await fetch_country_page(self._client, country.iso, now)
        if page is None or await _unchanged(page):
            return 0
        try:
            await ingest_document(to_document(page, page.content), models, store, allow_near_duplicate=True)
        except DuplicateDocumentError as error:
            logger.info("Odyseusz: %s duplicates %s", error.document_id, error.duplicate_of)
            return 0
        logger.info("Odyseusz: notice for %s indexed on demand", country.iso)
        return 1

    async def _fill(self, claim: str, models: EmbeddingModels, store: VectorStore) -> int:
        countries = [mention.country for mention in country_mentions(claim)]
        indexed = 0
        for country in countries[: settings.odyseusz_max_countries_per_claim]:
            try:
                indexed += await self._index_country(country, models, store)
            except OdyseuszError as error:
                logger.warning("Odyseusz: on-demand fetch for %s failed (%s)", country.iso, error)
        return indexed

    async def fill(self, claim: str, models: EmbeddingModels, store: VectorStore) -> OdyseuszFillResult:
        """
        Runs inside the search request for at most gov_search_budget_seconds, beside the gov.pl fill. A slower fill
        keeps running in the background, so the notice still reaches the corpus for the next question.
        """
        if not self.enabled:
            return OdyseuszFillResult(status="disabled")
        if not country_mentions(claim):
            return OdyseuszFillResult(status="skipped")
        task = asyncio.create_task(self._fill(claim, models, store))
        try:
            indexed = await asyncio.wait_for(asyncio.shield(task), settings.gov_search_budget_seconds)
        except TimeoutError:
            self._background.add(task)
            task.add_done_callback(self._finished_in_background)
            logger.info("Odyseusz on-demand fetch over budget, continues in the background")
            return OdyseuszFillResult(status="ok")
        except Exception:
            logger.exception("Odyseusz on-demand fetch failed")
            return OdyseuszFillResult(status="error")
        return OdyseuszFillResult(status="ok", indexed=indexed)

    def _finished_in_background(self, task: asyncio.Task) -> None:
        self._background.discard(task)
        if task.cancelled():
            return
        if (error := task.exception()) is not None:
            logger.warning("Odyseusz on-demand fetch in the background failed: %s", type(error).__name__)

    async def close(self) -> None:
        for task in self._background:
            task.cancel()
        await self._client.aclose()
