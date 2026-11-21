# Kontrakty między modułami

Zmiana tutaj wymaga wpisu w tym pliku w tym samym PR.

## front ↔ backend (HTTP)
TODO: `POST /api/check` — wejście (tekst lub URL), wyjście (lista twierdzeń z werdyktem, uzasadnieniem, siłą podstawy, źródłami, ograniczeniami albo osobny status błędu).

## backend ↔ agent
TODO: jedna funkcja `verify(input)` wywoływana tak samo przez każdy kanał.

## agent ↔ rag
TODO: `search(claim)` zwraca fragmenty z metadanymi (tytuł, wydawca, data publikacji, data pobrania, licencja, link).

## Statusy
Werdykty: `potwierdzone`, `falszywe`, `wprowadzajace_w_blad`, `brak_wystarczajacych_dowodow`, `nie_podlega_weryfikacji`.
Statusy niemerytoryczne (nie są werdyktem): `blad_techniczny`, `wymaga_doprecyzowania`, `poza_zakresem`.
