import asyncio

from app import corpus_sync, db
from app.corpus_rules import exclusion_reason, load_rules
from app.corpus_sync import prune_corpus, seed_urls

EXCLUDED = [
    ("https://www.zus.pl/", "Strona główna - ZUS"),
    ("https://demagog.org.pl/fake_news/", "Fake news pod kontrolą!"),
    ("https://www.gov.pl/web/premier", "Premier - Kancelaria Prezesa Rady Ministrów - Portal Gov.pl"),
    ("https://policja.pl/pol/aktualnosci/12345,Operacja-TOR.html", "Operacja TOR"),
    ("https://mazowiecka.policja.gov.pl/wra/aktualnosci/1", "Kradzież drewna w gminie Zatory"),
    ("https://kgsok.pl/aktualnosci/apel", "Uroczysty apel z okazji 108. rocznicy"),
    ("https://www.gov.pl/web/mon/news", "Aktualności (strona 2) - Ministerstwo Obrony Narodowej - Portal Gov.pl"),
    ("https://www.gov.pl/web/gis/x", "Ostrzeżenia - Główny Inspektorat Sanitarny - Portal Gov.pl"),
    ("https://demagog.org.pl/archiwum", "Weryfikacja wypowiedzi polityków - archiwum"),
    ("https://www.gov.pl/web/wody-polskie/komunikaty-nawigacyjne", "Komunikaty nawigacyjne - Wody Polskie"),
]
KEPT = [
    ("https://www.gov.pl/web/mswia/strefa", "Przedłużenie strefy buforowej na granicy polsko-białoruskiej"),
    ("https://www.gov.pl/web/gis/ostrzezenie-1", "Ostrzeżenie publiczne dotyczące żywności: pleśń"),
    ("https://moje.cert.pl/komunikaty/falszywe-sms", "Uwaga na fałszywe SMS-y o mandatach!"),
    ("https://www.gov.pl/web/infrastruktura/prawa-pasazerow", "Prawa pasażerów - Ministerstwo Infrastruktury"),
    ("https://dziennikustaw.gov.pl/DU/2026/1245", "Kodeks pracy (Dz.U. 2026 poz. 1245)"),
    ("https://demagog.org.pl/wypowiedzi/darmowa-komunikacja", "Darmowa komunikacja. Jaką kwotę musiałby dołożyć?"),
]


def test_rules_file_loads_with_all_three_kinds():
    rules = load_rules()
    assert rules.hosts and rules.url_patterns and rules.title_patterns


def test_listing_home_and_police_pages_are_excluded():
    for url, title in EXCLUDED:
        assert exclusion_reason(url, title) is not None, (url, title)


def test_articles_and_acts_are_kept():
    for url, title in KEPT:
        assert exclusion_reason(url, title) is None, (url, title)


def test_seed_urls_are_not_excluded_by_the_rules():
    assert [url for url in seed_urls() if exclusion_reason(url, "") is not None] == []


def test_prune_removes_only_documents_matching_the_rules(monkeypatch):
    rows = [
        {"document_id": "web:home", "url": "https://www.zus.pl/", "title": "Strona główna - ZUS"},
        {"document_id": "scrapped:9", "url": "https://policja.pl/pol/x", "title": "Pracownica banku wyłudziła"},
        {"document_id": "seed:zus", "url": "https://www.zus.pl/powszechny-wiek-emerytalny", "title": "Wiek emerytalny"},
    ]
    deleted: list[str] = []

    async def list_sources():
        return rows

    async def delete_document_chunks(document_id, store):
        deleted.append(document_id)
        return 3

    monkeypatch.setattr(db, "list_sources", list_sources)
    monkeypatch.setattr(corpus_sync, "delete_document_chunks", delete_document_chunks)

    report = asyncio.run(prune_corpus(store=None))

    assert deleted == ["web:home", "scrapped:9"]
    assert (report.documents_deleted, report.chunks_deleted) == (2, 6)
    assert report.document_ids == deleted
