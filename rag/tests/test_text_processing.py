from app.ingest import chunk_text
from app.languages import SuffixStemmer, load_profile
from app.query_expansion import expand_with_rules

MAX_CHARS = 100
OVERLAP = 20


def test_chunk_text_packs_paragraphs_up_to_limit():
    text = "Pierwszy akapit.\n\nDrugi akapit.\n\n" + "x" * 90
    chunks = chunk_text(text, MAX_CHARS, OVERLAP)
    assert chunks[0] == "Pierwszy akapit. Drugi akapit."
    assert all(len(chunk) <= MAX_CHARS for chunk in chunks)


def test_chunk_text_splits_oversize_paragraph_with_overlap():
    paragraph = "".join(str(index % 10) for index in range(250))
    chunks = chunk_text(paragraph, MAX_CHARS, OVERLAP)
    assert len(chunks) == 3
    assert chunks[0][-OVERLAP:] == chunks[1][:OVERLAP]


def test_chunk_text_skips_blank_paragraphs():
    assert chunk_text("\n\n   \n\nTekst", MAX_CHARS, OVERLAP) == ["Tekst"]


def test_polish_stemmer_maps_inflected_forms_to_same_stem():
    stemmer = load_profile("pl").stemmer
    assert stemmer.stem_word("ustawy") == stemmer.stem_word("ustawą") == stemmer.stem_word("ustawie")


def test_stemmer_keeps_minimum_stem_length():
    stemmer = SuffixStemmer(["owanie", "a"], min_stem_length=4)
    assert stemmer.stem_word("kota") == "kota"
    assert stemmer.stem_word("głosowanie") == "głos"


def test_rule_expansion_builds_statement_and_counter_query():
    queries = expand_with_rules("Czy poseł X poparł ustawę Y?")
    assert queries.neutral == "Poseł X poparł ustawę Y"
    assert queries.negative.startswith("Nieprawda, że poseł X poparł ustawę Y")
    assert queries.method == "rules"
