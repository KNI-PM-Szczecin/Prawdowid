from prawdowid_benchmark.metrics import BenchmarkMetrics, CompareMetrics

PERCENT = 100


def pct(value: float | None) -> str:
    return "brak danych" if value is None else f"{value * PERCENT:.1f}%"


def num(value: float | None, digits: int = 0) -> str:
    return "brak danych" if value is None else f"{value:.{digits}f}"


def _breakdown_table(title: str, rows: dict[str, dict[str, int]]) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| Grupa | n | poprawne | wstrzymania | szkodliwe | błędy |",
        "|---|---|---|---|---|---|",
    ]
    for name, counts in rows.items():
        lines.append(
            f"| {name} | {counts.get('n', 0)} | {counts.get('correct', 0)} | {counts.get('abstain', 0)} | "
            f"{counts.get('harmful', 0)} | {counts.get('error', 0)} |"
        )
    return [*lines, ""]


def render_report(meta: dict, metrics: BenchmarkMetrics) -> str:
    confusion = metrics.confusion
    without = metrics.confusion_without_self_reference
    lines = [
        "# Benchmark dezinformacji: wynik przebiegu",
        "",
        f"- Data: {meta['startedAt']}, commit `{meta['commit']}`, system `{meta['baseUrl']}`",
        f"- Zbiór: `{meta['datasetFile']}` (wersja {meta['datasetVersion']}, {metrics.claims_total} twierdzeń, "
        f"sha256 `{meta['datasetSha256'][:12]}`), powtórzenia: {meta['repeats']}",
        f"- Wersje korpusu: {', '.join(meta.get('corpusVersions', [])) or 'brak danych'}; "
        f"model systemu: {', '.join(meta.get('models', [])) or 'brak danych'}",
        "",
        "## Wykrywanie dezinformacji (binarne)",
        "",
        "Pozytywne = złota etykieta `false` lub `misleading`; negatywne = `confirmed`. Liczone na odpowiedziach "
        "rozstrzygniętych (bez wstrzymań i błędów).",
        "",
        "| | wszystkie | bez samoodniesienia |",
        "|---|---|---|",
        f"| TP (dezinformacja wykryta) | {confusion.tp} | {without.tp} |",
        f"| FP (prawda uznana za dezinformację) | {confusion.fp} | {without.fp} |",
        f"| TN (prawda potwierdzona) | {confusion.tn} | {without.tn} |",
        f"| FN (dezinformacja potwierdzona jako prawda) | {confusion.fn} | {without.fn} |",
        f"| Dokładność | {pct(confusion.accuracy)} | {pct(without.accuracy)} |",
        f"| Precyzja | {pct(confusion.precision)} | {pct(without.precision)} |",
        f"| Czułość | {pct(confusion.recall)} | {pct(without.recall)} |",
        f"| F1 | {pct(confusion.f1)} | {pct(without.f1)} |",
        "",
        "## Werdykt 4-klasowy i wstrzymania",
        "",
        "| Miernik | Wartość |",
        "|---|---|",
        f"| Dokładność (confirmed / false / misleading / not_verifiable) | {pct(metrics.accuracy_4class)} |",
        f"| Macro-F1 | {num(metrics.macro_f1_4class, 2)} |",
        f"| Odsetek rozstrzygnięć | {pct(metrics.decided_share)} |",
        f"| Wstrzymania ogółem | {pct(metrics.abstain_rate)} |",
        f"| Wstrzymania przy dezinformacji (zamiast wykryć) | {pct(metrics.abstain_on_positive)} |",
        f"| Wstrzymania przy prawdzie (zamiast potwierdzić) | {pct(metrics.abstain_on_negative)} |",
        f"| Szkodliwe odpowiedzi (dezinformacja potwierdzona) | {metrics.harmful_count} |",
        f"| Błędy techniczne / brak odpowiedzi | {metrics.error_count} |",
        f"| Samoodniesienie (cytuje weryfikację ze złotej etykiety) | {pct(metrics.self_reference_rate)} |",
        f"| Stabilność werdyktu przy powtórzeniach | {pct(metrics.stability)} |",
        "",
        "## Czas i koszt",
        "",
        "| Miernik | Wartość |",
        "|---|---|",
        f"| Średni czas odpowiedzi [ms] | {num(metrics.latency['mean'])} |",
        f"| Mediana czasu odpowiedzi [ms] | {num(metrics.latency['median'])} |",
        f"| p90 [ms] | {num(metrics.latency['p90'])} |",
        f"| Maksimum [ms] | {num(metrics.latency['max'])} |",
        f"| Mediana czasu po stronie serwera (meta.latencyMs) | {num(metrics.server_latency_median_ms)} |",
        f"| Średni koszt zapytania [USD] | {num(metrics.cost_mean_usd, 5)} |",
        f"| Koszt 100 zapytań [USD] | {num(metrics.cost_per_100_usd, 3)} |",
        "",
    ]
    if metrics.judge:
        judge = metrics.judge
        lines += [
            "## LLM jako sędzia",
            "",
            f"Model sędziego: `{meta.get('judgeModel', 'brak danych')}`, ocen: {judge['graded']}, "
            f"błędów sędziego: {judge['errors']}, tokeny: {judge['inputTokens']} wejściowych, "
            f"{judge['outputTokens']} wyjściowych.",
            "",
            "| Miernik | Wartość |",
            "|---|---|",
            f"| Werdykt zgodny lub uzasadnione wstrzymanie | {pct(judge['verdictOk'])} |",
            f"| Uzasadnione wstrzymania (wśród wstrzymań) | {pct(judge['abstainedJustified'])} |",
            f"| Cytaty wspierają werdykt (odpowiedzi ze źródłami) | {pct(judge['citationSupports'])} |",
            f"| Jakość uzasadnienia (0-2) | {num(judge['explanationQuality'], 2)} |",
            f"| Odpowiedzi szkodliwe | {pct(judge['harmful'])} |",
            f"| Zgodność sędzia-reguły | {pct(judge['agreementWithRules'])} "
            f"(kappa {num(judge['kappaWithRules'], 2)}) |",
            "",
            f"Rozbieżności sędzia-reguły ({len(metrics.judge_disagreements)}): "
            f"{', '.join(metrics.judge_disagreements) or 'brak'}",
            f"Sędzia niestabilny między powtórzeniami ({len(metrics.judge_unstable)}): "
            f"{', '.join(metrics.judge_unstable) or 'brak'}",
            "",
        ]
    lines += _breakdown_table("Według złotej etykiety", metrics.by_gold)
    lines += _breakdown_table("Według weryfikatora", metrics.by_reviewer)
    lines += _breakdown_table("Według tematu", metrics.by_topic)
    lines += [
        "## Jak czytać",
        "",
        "- Najgroźniejszy błąd to FN: dezinformacja potwierdzona jako prawda. Wstrzymanie się nie jest błędem, "
        "ale obniża odsetek rozstrzygnięć.",
        "- Kolumna „bez samoodniesienia” pokazuje wynik bez przypadków, w których system zacytował tę samą "
        "weryfikację, z której pochodzi etykieta.",
        "- Etykiety pochodzą od zewnętrznych weryfikatorów; sędzia LLM nie sprawdza faktów od nowa, tylko ocenia "
        "zgodność i uczciwość odpowiedzi. Tor ludzki (`human_review.csv`) kalibruje sędziego.",
        "",
    ]
    return "\n".join(lines)


def render_compare(meta: dict, metrics: CompareMetrics) -> str:
    interval = metrics.win_rate_ci
    lines = [
        "# Benchmark dezinformacji: porównanie A/B",
        "",
        f"- Data: {meta['startedAt']}, sędzia `{meta.get('judgeModel')}`",
        f"- A: `{meta['runA']}`",
        f"- B: `{meta['runB']}`",
        "",
        "Każda para oceniona dwa razy, w kolejności A/B i B/A. Wygrana liczy się tylko, gdy obie kolejności dają "
        "ten sam wynik; różnica między kolejnościami to uprzedzenie do pozycji.",
        "",
        "| Miernik | Wartość |",
        "|---|---|",
        f"| Pary | {metrics.pairs} |",
        f"| Wygrane A | {metrics.wins_a} |",
        f"| Wygrane B | {metrics.wins_b} |",
        f"| Remisy | {metrics.ties} |",
        f"| Niespójne (zależne od kolejności) | {metrics.inconsistent} |",
        f"| Błędy sędziego | {metrics.errors} |",
        f"| Odsetek wygranych A (wśród rozstrzygniętych) | {pct(metrics.win_rate_a)} |",
        f"| 95% przedział ufności | {pct(interval[0]) + ' - ' + pct(interval[1]) if interval else 'brak danych'} |",
        f"| Preferencja pierwszej pozycji | {pct(metrics.position_bias)} (50% = brak uprzedzenia) |",
        "",
    ]
    return "\n".join(lines)


def render_human(meta: dict, results: dict) -> str:
    lines = [
        "# Benchmark dezinformacji: ocena ludzka",
        "",
        f"- Przebieg: `{meta.get('runDir')}`, plik: `{meta.get('file')}`",
        f"- Wiersze: {results['rows']}, ocenione: {results['reviewed']}",
        "",
        "| Miernik | Wartość |",
        "|---|---|",
        f"| Werdykt poprawny (tak lub częściowo) | {pct(results['verdictCorrect'])} |",
        f"| Uzasadnione wstrzymania | {pct(results['abstentionJustified'])} |",
        f"| Cytaty wspierają werdykt | {pct(results['citationSupports'])} |",
        f"| Zrozumiałość uzasadnienia (1-3) | {num(results['explanationClear'], 2)} |",
        f"| Odpowiedzi szkodliwe | {pct(results['harmful'])} |",
        f"| Zgodność człowiek-sędzia LLM | {pct(results['agreementWithJudge'])} "
        f"(kappa {num(results['kappaWithJudge'], 2)}) |",
        "",
        f"Spory człowiek-sędzia ({len(results['disagreements'])}): {', '.join(results['disagreements']) or 'brak'}",
        "",
        "Zgodność poniżej 80% oznacza, że prompt sędziego wymaga poprawy; wyników systemu nie poprawiamy.",
        "",
    ]
    return "\n".join(lines)
