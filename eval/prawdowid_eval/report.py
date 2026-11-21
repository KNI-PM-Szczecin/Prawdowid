from prawdowid_eval.cases import Case
from prawdowid_eval.metrics import CaseOutcome, Metric

SCENARIO_NAMES = {
    "A": "Fakt prosty",
    "B": "Kontekst",
    "C": "Sprzeczność",
    "D": "Brak dowodów",
    "E": "Atak (prompt injection)",
    "F": "Multimodalność",
    "G": "Spójność kanałów",
    "H": "Pętla informacji",
    "I": "URL / incydent",
    "J": "Limit API / awaria",
}
PERCENT_METRIC_MARKERS = ("macro-F1", "Pokrycie", "Poprawność", "Wstrzymanie", "Odporność", "End-to-end", "Stabilność")
PERCENT = 100


def _format_value(metric: Metric, value: float | None) -> str:
    if value is None:
        return "brak danych"
    if "macro-F1" in metric.name:
        return f"{value:.2f}"
    if any(marker in metric.name for marker in PERCENT_METRIC_MARKERS):
        return f"{value * PERCENT:.0f}%"
    if "Koszt" in metric.name:
        return f"{value:.4f}"
    return f"{value:.0f}"


def _status_icon(metric: Metric) -> str:
    return {True: "✅", False: "❌", None: "—"}[metric.passed]


def render_report(
    run_meta: dict,
    cases: list[Case],
    metrics: list[Metric],
    outcomes: list[CaseOutcome],
    skipped: list[tuple[Case, str]],
) -> str:
    """Markdown report for the presentation; every number comes from results.json of the same run."""
    unreviewed = [case.id for case in cases if not case.reviewed and case.id in {o.case.id for o in outcomes}]
    lines = [
        "# Wyniki testów Prawdowid",
        "",
        f"- Data uruchomienia: {run_meta['startedAt']}",
        f"- Commit: `{run_meta['commit']}`, system: `{run_meta['baseUrl']}`",
        f"- Wersja korpusu: {', '.join(run_meta['corpusVersions']) or 'brak danych'}",
        f"- Model: {', '.join(run_meta['models']) or 'brak danych'}",
        f"- Przypadki: {len(outcomes)} uruchomionych, {len(skipped)} pominiętych, powtórzenia: {run_meta['repeats']}",
        f"- Plik przypadków: `{run_meta['casesFile']}` (sha256 `{run_meta['casesSha256'][:12]}`)",
        f"- Tryby: {', '.join(run_meta['enabled']) or 'domyślny'}",
        "",
    ]
    if unreviewed:
        lines += [
            f"> **Uwaga:** {len(unreviewed)} z {len(outcomes)} uruchomionych przypadków nie przeszło jeszcze "
            "przeglądu człowieka (`reviewed: false`). Wynik jest orientacyjny.",
            "",
        ]
    lines += [
        "## Mierniki obowiązkowe",
        "",
        "| Miernik | Wynik | Cel | Status | Próba | Uwagi |",
        "|---|---|---|---|---|---|",
    ]
    for metric in metrics:
        target = (
            "raportowany"
            if metric.target is None
            else ("≥ " if metric.higher_is_better else "≤ ") + _format_value(metric, metric.target)
        )
        lines.append(
            f"| {metric.name} | {_format_value(metric, metric.value)} | {target} | {_status_icon(metric)} "
            f"| {metric.sample_size} | {metric.detail} |"
        )

    lines += ["", "## Scenariusze z briefu", "", "| Scenariusz | Zaliczone | Pominięte |", "|---|---|---|"]
    for scenario, name in SCENARIO_NAMES.items():
        run = [outcome for outcome in outcomes if outcome.case.scenario == scenario]
        skip = [case for case, _ in skipped if case.scenario == scenario]
        passed = sum(outcome.passed for outcome in run)
        lines.append(f"| {scenario}. {name} | {passed}/{len(run)} | {len(skip)} |")

    failures = [outcome for outcome in outcomes if not outcome.passed]
    lines += ["", "## Niezaliczone przypadki", ""]
    if failures:
        lines += ["| Id | Oczekiwano | Otrzymano | Powód |", "|---|---|---|---|"]
        for outcome in failures:
            expected = outcome.case.expected.verdict or outcome.case.expected.status
            lines.append(f"| {outcome.case.id} | {expected} | {outcome.predicted} | {outcome.reason} |")
    else:
        lines.append("Brak.")

    lines += ["", "## Pominięte i nieobsługiwane", ""]
    if skipped:
        lines += ["| Id | Scenariusz | Powód |", "|---|---|---|"]
        lines += [f"| {case.id} | {case.scenario} | {reason} |" for case, reason in skipped]
    else:
        lines.append("Brak.")
    lines.append("")
    return "\n".join(lines)
