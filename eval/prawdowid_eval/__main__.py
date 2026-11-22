import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from prawdowid_eval.cases import load_cases, select_cases
from prawdowid_eval.metrics import citation_rows, compute_metrics
from prawdowid_eval.report import render_report
from prawdowid_eval.runner import RunRecord, run_cases, wait_until_ready

EVAL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CASES = EVAL_DIR / "cases.json"
DEFAULT_REPORTS = EVAL_DIR / "reports"
DEFAULT_BASE_URL = "http://localhost:3001"
DEFAULT_REPEATS = 1
RESULTS_FILE = "results.json"
REPORT_FILE = "report.md"
CITATIONS_FILE = "citations.csv"
CITATION_COLUMNS = ["case_id", "claim", "verdict", "source_id", "role", "title", "url", "quote", "supports"]
SUPPORTS_YES = {"tak", "t", "yes", "y", "1"}
SUPPORTS_NO = {"nie", "n", "no", "0"}
UNKNOWN_COMMIT = "nieznany"
EXIT_SYSTEM_UNREACHABLE = 2


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=EVAL_DIR
        )
    except (OSError, subprocess.CalledProcessError):
        return UNKNOWN_COMMIT
    return result.stdout.strip()


def _collect(records: list[RunRecord], key: str) -> list[str]:
    values = {
        str(record.body.get("meta", {}).get(key)) for record in records if record.body and record.body.get("meta")
    }
    return sorted(value for value in values if value != "None")


def _read_citation_labels(path: Path) -> dict[tuple[str, str], bool]:
    if not path.is_file():
        return {}
    labels: dict[tuple[str, str], bool] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            answer = row.get("supports", "").strip().lower()
            if answer in SUPPORTS_YES | SUPPORTS_NO:
                labels[(row["case_id"], row["source_id"])] = answer in SUPPORTS_YES
    return labels


def _write_report(run_dir: Path, cases_path: Path) -> Path:
    saved = json.loads((run_dir / RESULTS_FILE).read_text(encoding="utf-8"))
    if hashlib.sha256(cases_path.read_bytes()).hexdigest() != saved["meta"]["casesSha256"]:
        print(
            f"Uwaga: {cases_path.name} zmienił się od uruchomienia, raport może nie odpowiadać wynikom.",
            file=sys.stderr,
        )
    cases = load_cases(cases_path)
    records = [RunRecord.model_validate(record) for record in saved["records"]]
    selected_ids = saved["meta"].get("selectedIds")
    selected, skipped = select_cases(cases, set(saved["meta"]["enabled"]), set(selected_ids) if selected_ids else None)
    metrics, outcomes = compute_metrics(selected, records, _read_citation_labels(run_dir / CITATIONS_FILE))
    report_path = run_dir / REPORT_FILE
    report_path.write_text(render_report(saved["meta"], cases, metrics, outcomes, skipped), encoding="utf-8")
    return report_path


def command_run(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    only_ids = {case_id.strip() for case_id in args.ids.split(",")} if args.ids else None
    if only_ids is not None:
        unknown = sorted(only_ids - {case.id for case in cases})
        if unknown:
            print(f"Nieznane id przypadków: {', '.join(unknown)}", file=sys.stderr)
            return 1
    enabled = set(args.enable)
    selected, _ = select_cases(cases, enabled, only_ids)
    if not selected:
        print("Brak przypadków do uruchomienia w tym trybie.", file=sys.stderr)
        return 1

    if not wait_until_ready(args.url):
        print(f"System pod {args.url} nie jest gotowy (rag nie odpowiada). Raportu nie zapisano.", file=sys.stderr)
        return EXIT_SYSTEM_UNREACHABLE
    started_at = datetime.now(UTC)
    records = run_cases(args.url, selected, args.repeats)
    if all(record.body is None for record in records):
        print(f"System pod {args.url} nie odpowiedział na żadne zapytanie: {records[0].error}", file=sys.stderr)
        print("Raportu nie zapisano. Uruchom backend i powtórz.", file=sys.stderr)
        return EXIT_SYSTEM_UNREACHABLE
    run_dir = args.out / started_at.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)

    meta = {
        "startedAt": started_at.isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "baseUrl": args.url,
        "repeats": args.repeats,
        "enabled": sorted(enabled),
        "selectedIds": sorted(only_ids) if only_ids is not None else None,
        "casesFile": args.cases.name,
        "casesSha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "corpusVersions": _collect(records, "corpusVersion"),
        "models": _collect(records, "model"),
    }
    (run_dir / RESULTS_FILE).write_text(
        json.dumps(
            {"meta": meta, "records": [record.model_dump() for record in records]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    with (run_dir / CITATIONS_FILE).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CITATION_COLUMNS)
        writer.writeheader()
        writer.writerows(citation_rows(records))

    report_path = _write_report(run_dir, args.cases)
    print(f"Wyniki: {run_dir / RESULTS_FILE}\nRaport: {report_path}\nCytowania do oceny: {run_dir / CITATIONS_FILE}")
    return 0


def command_report(args: argparse.Namespace) -> int:
    report_path = _write_report(args.run_dir, args.cases)
    print(f"Raport: {report_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="prawdowid_eval", description="Testy Prawdowid według scenariuszy z briefu.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run", help="Uruchom przypadki na działającym systemie i policz metryki.")
    run_parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Adres backendu (POST /api/check).")
    run_parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    run_parser.add_argument("--out", type=Path, default=DEFAULT_REPORTS)
    run_parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS, help="Powtórzenia każdego przypadku.")
    run_parser.add_argument(
        "--enable",
        action="append",
        default=[],
        help="Włącz przypadki z danym requires, np. fault:no_llm_key, fault:rag_down, channel:discord.",
    )
    run_parser.add_argument(
        "--ids",
        default="",
        help=(
            "Uruchom tylko wskazane przypadki, np. --ids A01,I01 "
            "(spot-check: kilka realnych wywołań zamiast pełnego przebiegu)."
        ),
    )
    run_parser.set_defaults(handler=command_run)

    report_parser = subcommands.add_parser("report", help="Przelicz raport z zapisanego results.json i citations.csv.")
    report_parser.add_argument("run_dir", type=Path)
    report_parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    report_parser.set_defaults(handler=command_report)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
