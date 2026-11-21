import asyncio
import re
from datetime import UTC, datetime

from app import corpus_sync, db, law_import
from app.law_import import (
    ActSpec,
    ActVersion,
    act_pages,
    act_text,
    act_url,
    import_law,
    join_wrapped_lines,
    load_act_specs,
    newest_version,
    split_text,
)

NOW = datetime(2026, 11, 22, tzinfo=UTC)
# Dz.U. titles join "ustawy" and the act name with an en dash.
DASH = chr(0x2013)
KODEKS_PRACY = ActSpec("kodeks-pracy", "Kodeks pracy", re.compile(rf"tekstu ustawy [{DASH}-] Kodeks pracy$", re.I))
KODEKS_KARNY = ActSpec("kodeks-karny", "Kodeks karny", re.compile(rf"ustawy [{DASH}-] Kodeks karny$", re.I))
TITLE = f"OBWIESZCZENIE MARSZAŁKA SEJMU z dnia {{}} w sprawie ogłoszenia jednolitego tekstu ustawy {DASH} {{}}"
CANDIDATES = [
    ActVersion(277, 2025, datetime(2025, 3, 6, tzinfo=UTC), TITLE.format("14 lutego 2025 r.", "Kodeks pracy")),
    ActVersion(1245, 2026, datetime(2026, 9, 24, tzinfo=UTC), TITLE.format("1 września 2026 r.", "Kodeks pracy1)")),
    ActVersion(633, 2025, datetime(2025, 5, 15, tzinfo=UTC), TITLE.format("10 kwietnia", "Kodeks karny skarbowy")),
    ActVersion(1342, 2026, datetime(2026, 10, 16, tzinfo=UTC), TITLE.format("2 października", "Kodeks karny")),
]


def test_act_specs_are_unique_and_compile():
    specs = load_act_specs()
    assert len(specs) >= 30
    assert len({spec.id for spec in specs}) == len(specs)


def test_newest_version_matches_exact_act_name_and_ignores_footnote_marks():
    assert newest_version(KODEKS_PRACY, CANDIDATES).position == 1245
    assert newest_version(KODEKS_KARNY, CANDIDATES).position == 1342
    assert newest_version(ActSpec("x", "x", re.compile("Konstytucja")), CANDIDATES) is None


def test_act_url_points_to_the_dziennik_ustaw_position():
    assert act_url(CANDIDATES[1]) == "https://dziennikustaw.gov.pl/DU/2026/1245"


def test_wrapped_pdf_lines_are_joined_but_enumerations_stay():
    rule = "Art. 1. Dniami wolnymi od pracy są:\n1) dni niżej wymienione:\na) 1 stycznia,\nb) 6 stycz-\nnia"
    joined = join_wrapped_lines(rule)
    assert joined == "Art. 1. Dniami wolnymi od pracy są:\n1) dni niżej wymienione:\na) 1 stycznia,\nb) 6 stycznia"
    assert join_wrapped_lines("Art. 2. Ustawa wchodzi\nw życie.") == "Art. 2. Ustawa wchodzi w życie."


def test_act_text_starts_with_the_title_and_separates_articles():
    text = act_text(CANDIDATES[1], ["Art. 1. A.", "", "Art. 2. B."])
    assert text.startswith("OBWIESZCZENIE MARSZAŁKA SEJMU")
    assert text.endswith("Kodeks pracy\n\nArt. 1. A.\n\nArt. 2. B.")


def test_split_text_keeps_paragraphs_whole():
    text = "\n\n".join(f"Art. {index}. " + "x" * 90 for index in range(1, 11))
    parts = split_text(text, max_chars=300)
    assert "".join(parts).count("Art.") == 10
    assert all(len(part) <= 300 for part in parts)
    assert all(part.startswith("Art.") for part in parts)


def test_act_pages_split_long_acts_into_numbered_parts_with_stable_ids():
    rules = ["Art. 1. " + "a" * 100, "Art. 2. " + "b" * 100, "Art. 3. " + "c" * 100]
    pages = act_pages(KODEKS_PRACY, CANDIDATES[1], rules, NOW, max_part_chars=260)
    assert [page.document_id for page in pages] == ["law:kodeks-pracy", "law:kodeks-pracy:2"]
    assert pages[0].title == "Kodeks pracy (Dz.U. 2026 poz. 1245), część 1 z 2"
    assert pages[0].published_at == datetime(2026, 9, 24, tzinfo=UTC)
    assert pages[0].license and pages[0].url == "https://dziennikustaw.gov.pl/DU/2026/1245"
    single = act_pages(KODEKS_PRACY, CANDIDATES[1], rules[:1], NOW, max_part_chars=10_000)
    assert single[0].title == "Kodeks pracy (Dz.U. 2026 poz. 1245)"


def test_import_respects_budget_and_skips_acts_already_indexed(monkeypatch):
    specs = [KODEKS_PRACY, KODEKS_KARNY, ActSpec("brak", "Brak", re.compile("Konstytucja"))]
    ingested: list[str] = []

    async def fetch_law_acts():
        return [
            {"position": act.position, "year": act.year, "date": int(act.date.strftime("%Y%m%d")), "title": act.title}
            for act in CANDIDATES
        ]

    async def fetch_law_rules(position, year):
        return [f"Art. 1. Akt {position}/{year}.", "Art. 2. " + "x" * 50]

    async def active_document_url(document_id):
        return "https://dziennikustaw.gov.pl/DU/2026/1245" if document_id == "law:kodeks-pracy" else None

    async def ingest_document(document, models, store):
        ingested.append(document.source.document_id)

    monkeypatch.setattr(law_import, "load_act_specs", lambda: specs)
    monkeypatch.setattr(db, "fetch_law_acts", fetch_law_acts)
    monkeypatch.setattr(db, "fetch_law_rules", fetch_law_rules)
    monkeypatch.setattr(db, "active_document_url", active_document_url)
    monkeypatch.setattr(corpus_sync, "ingest_document", ingest_document)

    state = asyncio.run(import_law(models=None, store=None, max_chars=10_000, max_part_chars=10_000))

    assert ingested == ["law:kodeks-karny"]
    assert (state.indexed, state.already_present, state.failed) == (1, 1, 1)

    ingested.clear()
    state = asyncio.run(import_law(models=None, store=None, max_chars=10, max_part_chars=10_000))
    assert ingested == [] and state.indexed == 0
