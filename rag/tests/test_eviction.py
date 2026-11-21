from uuid import UUID, uuid4

from app.eviction import EvictionCandidate, select_evictions

NO_FLOOR = 0


def _corpus(documents_per_domain: dict[str, int], chunks_per_document: int):
    candidates: list[EvictionCandidate] = []
    chunk_counts: dict[str, int] = {}
    domains: dict[str, str] = {}
    for domain, document_count in documents_per_domain.items():
        for index in range(document_count):
            document = f"{domain}-{index}"
            chunk_counts[document] = chunks_per_document
            domains[document] = domain
            candidates.extend(EvictionCandidate(uuid4(), document) for _ in range(chunks_per_document))
    return candidates, chunk_counts, domains


def _documents_left(selected: list[UUID], candidates, chunk_counts) -> int:
    removed = {candidate.chunk_id for candidate in candidates if candidate.chunk_id in set(selected)}
    left = dict(chunk_counts)
    for candidate in candidates:
        if candidate.chunk_id in removed:
            left[candidate.document_id] -= 1
    return sum(1 for count in left.values() if count > 0)


def test_takes_only_the_excess_in_candidate_order():
    candidates, chunk_counts, domains = _corpus({"a.pl": 5}, chunks_per_document=2)
    selected = select_evictions(candidates, chunk_counts, domains, 3, NO_FLOOR, NO_FLOOR)
    assert selected == [candidate.chunk_id for candidate in candidates[:3]]


def test_never_drops_below_minimum_documents():
    candidates, chunk_counts, domains = _corpus({"a.pl": 6}, chunks_per_document=1)
    selected = select_evictions(candidates, chunk_counts, domains, 6, min_documents=4, min_domains=NO_FLOOR)
    assert len(selected) == 2
    assert _documents_left(selected, candidates, chunk_counts) == 4


def test_never_removes_last_document_of_domain_at_minimum_domains():
    candidates, chunk_counts, domains = _corpus({"a.pl": 1, "b.pl": 1, "c.pl": 3}, chunks_per_document=1)
    selected = select_evictions(candidates, chunk_counts, domains, 5, min_documents=NO_FLOOR, min_domains=3)
    evicted_domains = {domains[c.document_id] for c in candidates if c.chunk_id in selected}
    assert evicted_domains == {"c.pl"}
    assert len(selected) == 2


def test_multi_chunk_documents_can_lose_chunks_at_document_floor():
    candidates, chunk_counts, domains = _corpus({"a.pl": 2}, chunks_per_document=3)
    selected = select_evictions(candidates, chunk_counts, domains, 6, min_documents=2, min_domains=NO_FLOOR)
    assert len(selected) == 4
    assert _documents_left(selected, candidates, chunk_counts) == 2
