package agent

import (
	"strings"
	"testing"
)

const (
	announcementChunk = "55555555-5555-5555-5555-555555555555"
	otherCityChunk    = "66666666-6666-6666-6666-666666666666"
	undatedChunk      = "77777777-7777-7777-7777-777777777777"
	claimBridge       = "W Zielonowie ostatnio zamknięto most na rzece Lipce."
)

// Fictional sources: an announcement that does not say whether the event happened, a page about another town and a
// passage without a publication date (not enough metadata to be shown).
func announcementPassage() Passage {
	published := "2026-11-10T00:00:00Z"
	return Passage{
		DocumentID: "urzad-zielonowo-1", Title: "Komunikat o moście", Publisher: "Urząd Miasta Zielonowo", PublishedAt: &published,
		FetchedAt: "2026-11-21T00:00:00Z", URL: "https://zielonowo.example.gov.pl/most", SourceType: SourceTypeOfficial,
		Passage: "Urząd Miasta Zielonowo zapowiada zamknięcie mostu na rzece Lipce na 18 listopada. " +
			"Objazd poprowadzi ulicą Polną. " + strings.Repeat("Szczegóły objazdu podamy w osobnym komunikacie dla mieszkańców. ", 6),
		Score: 0.6, Flags: []string{}, ChunkID: announcementChunk,
	}
}

func otherCityPassage() Passage {
	published := "2025-05-02T00:00:00Z"
	return Passage{
		DocumentID: "portal-borowo-1", Title: "Remont w Borowie", Publisher: "Gazeta Borowska", PublishedAt: &published,
		FetchedAt: "2026-11-21T00:00:00Z", URL: "https://borowo.example/remont", SourceType: SourceTypeSecondary,
		Passage: "W Borowie zamknięto most na czas remontu, który potrwa do wiosny.",
		Score:   0.4, Flags: []string{}, ChunkID: otherCityChunk,
	}
}

func undatedPassage() Passage {
	return Passage{
		DocumentID: "blog-1", Title: "Wpis", Publisher: "Blog", FetchedAt: "2026-11-21T00:00:00Z",
		URL: "https://blog.example/wpis", SourceType: SourceTypeSecondary,
		Passage: "Mosty w regionie są zamykane coraz częściej, piszą mieszkańcy.",
		Score:   0.9, Flags: []string{}, ChunkID: undatedChunk,
	}
}

const abstainWithoutCitations = `{"werdykt":"brak_dowodow","uzasadnienie":"Źródła mówią o zapowiedzi, nie o tym, czy most zamknięto.",` +
	`"cytaty":[],"brakuje":"Nie wiadomo, czy zamknięcie się odbyło.","podejrzane":false}`

func TestAbstentionWithoutCitationsShowsBestPassagesAsContext(t *testing.T) {
	rag := &ragStub{search: searchWith(otherCityPassage(), undatedPassage(), announcementPassage())}
	result := verify(t, newTestAgent(t, &fakeProvider{judge: abstainWithoutCitations}, rag), claimBridge, InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictInsufficientEvidence || claim.EvidenceStrength != StrengthWeak {
		t.Fatalf("expected a weak abstention, got %s %s", claim.Verdict, claim.EvidenceStrength)
	}
	if len(claim.Sources) != maxFallbackSources || claim.Sources[0].ID != announcementChunk || claim.Sources[1].ID != otherCityChunk {
		t.Fatalf("expected the two best dated passages by score, got %+v", claim.Sources)
	}
	passages := map[string]Passage{announcementChunk: announcementPassage(), otherCityChunk: otherCityPassage()}
	for _, source := range claim.Sources {
		if source.Role != RoleContext || source.PublishedAt == nil || source.Title == "" || source.URL == "" {
			t.Fatalf("a fallback source must be context with full metadata: %+v", source)
		}
		if !quoteInPassage(source.Quote, passages[source.ID].Passage) || len([]rune(source.Quote)) > maxFallbackQuoteRunes {
			t.Fatalf("the quote must be a verbatim, bounded part of the passage: %q", source.Quote)
		}
	}
	if !strings.HasSuffix(claim.Sources[0].Quote, ".") {
		t.Fatalf("a long passage is cut after a full sentence: %q", claim.Sources[0].Quote)
	}
	if claim.Missing == nil || *claim.Missing != "Nie wiadomo, czy zamknięcie się odbyło." || !result.Meta.Abstained {
		t.Fatalf("missing/meta: %v %+v", claim.Missing, result.Meta)
	}
}

func TestFallbackNeedsDatedPassages(t *testing.T) {
	rag := &ragStub{search: searchWith(undatedPassage())}
	result := verify(t, newTestAgent(t, &fakeProvider{judge: abstainWithoutCitations}, rag), claimBridge, InputTypeText)
	if claim := result.Claims[0]; len(claim.Sources) != 0 || claim.EvidenceStrength != StrengthNone {
		t.Fatalf("a passage without a date must not be shown as a source: %+v", claim)
	}
}

func TestDecisiveVerdictGetsNoFallbackSources(t *testing.T) {
	provider := &fakeProvider{judge: judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza")}
	rag := &ragStub{search: searchWith(officialPassage(), announcementPassage())}
	result := verify(t, newTestAgent(t, provider, rag), claimSejm, InputTypeText)
	if claim := result.Claims[0]; claim.Verdict != VerdictConfirmed || len(claim.Sources) != 1 || claim.Sources[0].ID != officialChunk {
		t.Fatalf("a confirmed claim keeps only its cited source: %+v", claim)
	}
}

// A source about another town is context, not a refutation: misleading needs a decisive citation.
func TestMisleadingWithOnlyContextCitationAbstains(t *testing.T) {
	judge := `{"werdykt":"wprowadzajace_w_blad","uzasadnienie":"Most zamknięto w innym mieście.","cytaty":[{"id":"` + otherCityChunk +
		`","cytat":"W Borowie zamknięto most na czas remontu","rola":"kontekst"}],"brakuje":null,"podejrzane":false}`
	rag := &ragStub{search: searchWith(otherCityPassage())}
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judge}, rag), claimBridge, InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictInsufficientEvidence || claim.Missing == nil || *claim.Missing != missingWeakEvidence {
		t.Fatalf("expected an abstention, got %s %v", claim.Verdict, claim.Missing)
	}
	if len(claim.Sources) != 1 || claim.Sources[0].Role != RoleContext || claim.Sources[0].Quote != "W Borowie zamknięto most na czas remontu" {
		t.Fatalf("the cited context stays, without fallback additions: %+v", claim.Sources)
	}
}

func TestDecideMisleadingNeedsDecisiveCitationOrAgreeingRating(t *testing.T) {
	context := []SourceRef{{ID: "x", Role: RoleContext, SourceType: SourceTypeSecondary}}
	refuting := []SourceRef{{ID: "x", Role: RoleRefutes, SourceType: SourceTypeSecondary}}
	tests := []struct {
		name    string
		sources []SourceRef
		ruling  factcheckRuling
		want    string
	}{
		{"context only", context, factcheckRuling{}, VerdictInsufficientEvidence},
		{"refuting citation", refuting, factcheckRuling{}, VerdictMisleading},
		{"agreeing fact-check rating", context, factcheckRuling{agrees: true}, VerdictMisleading},
	}
	for _, test := range tests {
		ev := assessEvidence(test.sources, fixedNow)
		if got := decide("c1", VerdictMisleading, nil, test.sources, ev, 0, test.ruling); got.verdict != test.want {
			t.Errorf("%s: got %s, want %s", test.name, got.verdict, test.want)
		}
	}
	ev := assessEvidence(context, fixedNow)
	if got := decide("c1", VerdictFalse, nil, context, ev, 0, factcheckRuling{}); got.verdict != VerdictInsufficientEvidence {
		t.Errorf("false without a refuting citation: got %s", got.verdict)
	}
}

func TestMisleadingFactcheckRatingStillGivesMisleading(t *testing.T) {
	passage := factcheckPassage()
	passage.Passage = strings.Replace(passage.Passage, "Fałsz", "Manipulacja", 1)
	judge := `{"werdykt":"wprowadzajace_w_blad","uzasadnienie":"Według Demagoga to manipulacja.","cytaty":[{"id":"` + factcheckChk +
		`","cytat":"Ocena weryfikatora (Demagog): Manipulacja","rola":"kontekst"}],"brakuje":null,"podejrzane":false}`
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judge}, &ragStub{search: searchWith(passage)}), claimSejm, InputTypeText)
	if claim := result.Claims[0]; claim.Verdict != VerdictMisleading {
		t.Fatalf("an agreeing misleading rating keeps the verdict, got %+v", claim)
	}
}

// A claim about the check itself is confirmed by the fact-check's existence, whatever its rating.
func TestClaimAboutFactcheckIsConfirmedByTheCheck(t *testing.T) {
	judge := `{"werdykt":"potwierdzone","uzasadnienie":"Tak, Demagog to sprawdził i ocenił jako fałsz.","cytaty":[{"id":"` + factcheckChk +
		`","cytat":"Twierdzenie sprawdzone przez weryfikatora faktów: Kadencja Sejmu trwa 4 lata","rola":"potwierdza"}],"brakuje":null,"podejrzane":false}`
	rag := &ragStub{search: searchWith(factcheckPassage())}
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judge}, rag), "Demagog sprawdzał, czy kadencja Sejmu trwa 4 lata.", InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictConfirmed || claim.EvidenceStrength != StrengthStrong || claim.Sources[0].Role != RoleSupports {
		t.Fatalf("expected confirmed with the fact-check as support, got %+v", claim)
	}
	if len(result.Limitations) != 0 {
		t.Fatalf("the rating must not be read as a conflict, got %v", result.Limitations)
	}
}

func TestIsFactcheckMetaClaim(t *testing.T) {
	cases := []struct {
		claim      string
		publishers []string
		want       bool
	}{
		{"Demagog sprawdzał, czy kadencja Sejmu trwa 4 lata.", []string{"Demagog"}, true},
		{"Weryfikatorzy faktów sprawdzili tę wypowiedź.", nil, true},
		{"Portal Prawdomir zweryfikował informację o moście.", []string{"Prawdomir"}, true},
		{"Kadencja Sejmu trwa 4 lata.", []string{"Demagog"}, false},
		{"Demagog to stowarzyszenie z Gdańska.", []string{"Demagog"}, false},
		{"NIK sprawdziła wydatki gminy.", []string{"Demagog", ""}, false},
		{"Demagog ocenił wypowiedź o moście jako prawdziwą.", []string{"Demagog"}, false},
	}
	for _, test := range cases {
		if got := isFactcheckMetaClaim(test.claim, test.publishers...); got != test.want {
			t.Errorf("%q: got %v, want %v", test.claim, got, test.want)
		}
	}
}

func TestPassageOpeningCutsOnBoundaries(t *testing.T) {
	short := "Krótki fragment źródła."
	if got := passageOpening("  "+short+"  ", maxFallbackQuoteRunes); got != short {
		t.Fatalf("a short passage is quoted whole, got %q", got)
	}
	sentences := "Pierwsze zdanie jest tutaj. Drugie zdanie jest znacznie dłuższe i nie zmieści się w limicie znaków."
	if got := passageOpening(sentences, 40); got != "Pierwsze zdanie jest tutaj." {
		t.Fatalf("expected a cut after the sentence, got %q", got)
	}
	words := "Bardzo długie zdanie bez kropki które ciągnie się i ciągnie przez wiele słów"
	got := passageOpening(words, 30)
	if !strings.HasPrefix(words, got) || strings.HasSuffix(got, " ") || words[len(got)] != ' ' {
		t.Fatalf("expected a cut on a word boundary, got %q", got)
	}
}
