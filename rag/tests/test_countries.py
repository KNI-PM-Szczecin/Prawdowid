import pytest

from app.countries import country_mentions, nominative_forms


def _names(text: str) -> list[str]:
    return sorted(mention.country.name for mention in country_mentions(text))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pociągi nie jeżdżą w Szwecji.", ["Szwecja"]),
        ("Turyści z Francji wracają.", ["Francja"]),
        ("Upały w Hiszpanii.", ["Hiszpania"]),
        ("Wybory w Niemczech i na Węgrzech.", ["Niemcy", "Węgry"]),
        ("Lotnisko na Malcie i w Egipcie.", ["Egipt", "Malta"]),
        ("Cła w Stanach Zjednoczonych.", ["Stany Zjednoczone (USA)"]),
        ("Protest w USA.", ["Stany Zjednoczone (USA)"]),
        ("Susza w Sudanie Południowym.", ["Sudan Południowy"]),
        ("czy w portugalii pada", ["Portugalia"]),
    ],
)
def test_inflected_country_names_are_recognised(text, expected):
    assert _names(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Maltretowanie zwierząt jest karalne.",
        "Zatrucie czadem w bloku na Pomorzu.",
        "Sprzedawca malin z Mazur.",
        "Cechy dobrego wniosku.",
    ],
)
def test_ordinary_words_are_not_countries(text):
    assert country_mentions(text) == []


def test_nominative_forms_map_inflected_words_to_the_name():
    assert nominative_forms("Strajk na Węgrzech i w Stanach Zjednoczonych") == {
        "węgrzech": "Węgry",
        "stanach": "Stany",
        "zjednoczonych": "Zjednoczone",
    }
