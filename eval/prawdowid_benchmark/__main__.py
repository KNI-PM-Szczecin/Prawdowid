import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from prawdowid_benchmark.dataset import build_dataset, load_dataset, load_topics, save_json
from prawdowid_benchmark.human import human_metrics, read_sample, select_sample, write_sample
from prawdowid_benchmark.judge import (
    AnthropicJudge,
    compare_runs,
    judge_records,
    load_compare_records,
    load_judge_records,
)
from prawdowid_benchmark.metrics import compare_metrics, compute_metrics
from prawdowid_benchmark.report import render_compare, render_human, render_report
from prawdowid_benchmark.runner import run_claims
from prawdowid_eval.runner import RunRecord

EVAL_DIR = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = EVAL_DIR / "benchmark"
DEFAULT_DATASET = BENCHMARK_DIR / "dataset.json"
DEFAULT_REJECTED = BENCHMARK_DIR / "dataset_rejected.json"
DEFAULT_TOPICS = BENCHMARK_DIR / "topics.json"
DEFAULT_RUNS = BENCHMARK_DIR / "runs"
DOTENV_PATH = EVAL_DIR.parent / ".env"
DEFAULT_BASE_URL = "http://localhost:3001"
DEFAULT_SIZE = 200
DEFAULT_SEED = 2026
DEFAULT_REPEATS = 1
DEFAULT_JUDGE_REPEATS = 2
RESULTS_FILE = "results.json"
JUDGE_FILE = "judge.json"
METRICS_FILE = "metrics.json"
REPORT_FILE = "report.md"
COMPARE_FILE = "compare.json"
COMPARE_REPORT_FILE = "compare.md"
HUMAN_FILE = "human_review.csv"
HUMAN_REPORT_FILE = "human_report.md"
FACTCHECK_KEY_ENV = "FACTCHECK_API_KEY"
UNKNOWN_COMMIT = "nieznany"
EXIT_SYSTEM_UNREACHABLE = 2


def load_dotenv(path: Path) -> None:
    """Reads KEY=value lines from the repo's .env into the environment without overriding what is already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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


def _progress(done: int, total: int) -> None:
    if done % 10 == 0 or done == total:
        print(f"  {done}/{total}", file=sys.stderr)


def _read_run(run_dir: Path) -> tuple[dict, list[RunRecord]]:
    saved = json.loads((run_dir / RESULTS_FILE).read_text(encoding="utf-8"))
    return saved["meta"], [RunRecord.model_validate(record) for record in saved["records"]]


def _dataset_for_run(meta: dict, dataset_path: Path):
    dataset = load_dataset(dataset_path)
    if hashlib.sha256(dataset_path.read_bytes()).hexdigest() != meta["datasetSha256"]:
        print(
            f"Uwaga: {dataset_path.name} zmienił się od przebiegu; raport może nie odpowiadać wynikom.", file=sys.stderr
        )
    return dataset


def _write_report(run_dir: Path, dataset_path: Path) -> Path:
    meta, records = _read_run(run_dir)
    dataset = _dataset_for_run(meta, dataset_path)
    judge_path = run_dir / JUDGE_FILE
    judged = load_judge_records(judge_path) if judge_path.is_file() else None
    metrics = compute_metrics(dataset.claims, records, judged)
    summary = {
        "confusion": vars(metrics.confusion),
        "confusionWithoutSelfReference": vars(metrics.confusion_without_self_reference),
        "accuracy4class": metrics.accuracy_4class,
        "macroF1": metrics.macro_f1_4class,
        "decidedShare": metrics.decided_share,
        "abstainRate": metrics.abstain_rate,
        "harmfulCount": metrics.harmful_count,
        "errorCount": metrics.error_count,
        "latencyMs": metrics.latency,
        "costPer100Usd": metrics.cost_per_100_usd,
        "selfReferenceRate": metrics.self_reference_rate,
        "judge": metrics.judge,
    }
    (run_dir / METRICS_FILE).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = run_dir / REPORT_FILE
    report_path.write_text(render_report(meta, metrics), encoding="utf-8")
    return report_path


def command_build_dataset(args: argparse.Namespace) -> int:
    api_key = os.environ.get(FACTCHECK_KEY_ENV)
    if not api_key:
        print(f"Brak {FACTCHECK_KEY_ENV} w środowisku ani w {DOTENV_PATH}.", file=sys.stderr)
        return 1
    topics = load_topics(args.topics)
    dataset, rejected = build_dataset(api_key, topics, args.size, args.seed)
    save_json(args.out, dataset)
    save_json(args.rejected, rejected)
    by_gold = {}
    for claim in dataset.claims:
        by_gold[claim.gold] = by_gold.get(claim.gold, 0) + 1
    print(
        f"Zbiór: {args.out} ({dataset.size} twierdzeń, rozkład {by_gold}); odrzucone: {args.rejected} ({len(rejected)})"
    )
    return 0


def command_run(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    claims = dataset.claims[: args.limit] if args.limit else dataset.claims
    started_at = datetime.now(UTC)
    records = run_claims(args.url, claims, args.repeats)
    if all(record.body is None for record in records):
        print(f"System pod {args.url} nie odpowiedział na żadne zapytanie: {records[0].error}", file=sys.stderr)
        return EXIT_SYSTEM_UNREACHABLE
    run_dir = args.out / started_at.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    meta = {
        "startedAt": started_at.isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "baseUrl": args.url,
        "repeats": args.repeats,
        "limit": args.limit,
        "datasetFile": args.dataset.name,
        "datasetVersion": dataset.version,
        "datasetSha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "corpusVersions": _collect(records, "corpusVersion"),
        "models": _collect(records, "model"),
    }
    (run_dir / RESULTS_FILE).write_text(
        json.dumps(
            {"meta": meta, "records": [record.model_dump() for record in records]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    report_path = _write_report(run_dir, args.dataset)
    print(f"Wyniki: {run_dir / RESULTS_FILE}\nRaport (bez sędziego): {report_path}")
    return 0


def command_judge(args: argparse.Namespace) -> int:
    meta, records = _read_run(args.run_dir)
    dataset = _dataset_for_run(meta, args.dataset)
    judge = AnthropicJudge(model=args.model)
    print(f"Sędzia: {judge.model}, ocen: {len(records)} x {args.judge_repeats}", file=sys.stderr)
    results = judge_records(dataset.claims, records, judge, args.judge_repeats, progress=_progress)
    (args.run_dir / JUDGE_FILE).write_text(
        json.dumps([record.model_dump(by_alias=True) for record in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    saved = json.loads((args.run_dir / RESULTS_FILE).read_text(encoding="utf-8"))
    saved["meta"]["judgeModel"] = judge.model
    saved["meta"]["judgeRepeats"] = args.judge_repeats
    (args.run_dir / RESULTS_FILE).write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = _write_report(args.run_dir, args.dataset)
    errors = sum(1 for record in results if record.assessment is None)
    print(f"Oceny sędziego: {args.run_dir / JUDGE_FILE} (błędów: {errors})\nRaport: {report_path}")
    return 0


def command_report(args: argparse.Namespace) -> int:
    print(f"Raport: {_write_report(args.run_dir, args.dataset)}")
    return 0


def command_compare(args: argparse.Namespace) -> int:
    meta_a, records_a = _read_run(args.run_a)
    meta_b, records_b = _read_run(args.run_b)
    if meta_a["datasetSha256"] != meta_b["datasetSha256"]:
        print("Przebiegi mają różne zbiory; porównanie wymaga tego samego dataset.json.", file=sys.stderr)
        return 1
    dataset = _dataset_for_run(meta_a, args.dataset)
    judge = AnthropicJudge(model=args.model)
    print(f"Sędzia: {judge.model}; par: {len(dataset.claims)}, ocen: {2 * len(dataset.claims)}", file=sys.stderr)
    results = compare_runs(dataset.claims, records_a, records_b, judge, progress=_progress)
    out_dir = args.out / datetime.now(UTC).strftime("%Y%m%d-%H%M%S-compare")
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / COMPARE_FILE).write_text(
        json.dumps([record.model_dump(by_alias=True) for record in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    meta = {
        "startedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "judgeModel": judge.model,
        "runA": str(args.run_a),
        "runB": str(args.run_b),
    }
    report_path = out_dir / COMPARE_REPORT_FILE
    report_path.write_text(render_compare(meta, compare_metrics(results)), encoding="utf-8")
    print(f"Porównanie: {report_path}")
    return 0


def command_compare_report(args: argparse.Namespace) -> int:
    results = load_compare_records(args.compare_dir / COMPARE_FILE)
    meta = {"startedAt": "z pliku", "judgeModel": results[0].model if results else None, "runA": "?", "runB": "?"}
    report_path = args.compare_dir / COMPARE_REPORT_FILE
    report_path.write_text(render_compare(meta, compare_metrics(results)), encoding="utf-8")
    print(f"Porównanie: {report_path}")
    return 0


def command_human_sample(args: argparse.Namespace) -> int:
    meta, records = _read_run(args.run_dir)
    dataset = _dataset_for_run(meta, args.dataset)
    judge_path = args.run_dir / JUDGE_FILE
    judged = load_judge_records(judge_path) if judge_path.is_file() else []
    metrics = compute_metrics(dataset.claims, records, judged or None)
    sample = select_sample(metrics, judged, args.seed)
    path = args.run_dir / HUMAN_FILE
    write_sample(path, sample, judged)
    print(f"Próbka do oceny ludzkiej: {path} ({len(sample)} wierszy). Instrukcja: benchmark/human_review_guide.md")
    return 0


def command_human_report(args: argparse.Namespace) -> int:
    files = sorted(args.run_dir.glob("human_review*.csv"))
    if not files:
        print(f"Brak plików human_review*.csv w {args.run_dir}.", file=sys.stderr)
        return 1
    sections = []
    for path in files:
        results = human_metrics(read_sample(path))
        sections.append(render_human({"runDir": str(args.run_dir), "file": path.name}, results))
    report_path = args.run_dir / HUMAN_REPORT_FILE
    report_path.write_text("\n\n".join(sections), encoding="utf-8")
    print(f"Raport ludzki: {report_path}")
    return 0


def main() -> int:
    load_dotenv(DOTENV_PATH)
    parser = argparse.ArgumentParser(prog="prawdowid_benchmark", description="Benchmark dezinformacji Prawdowid.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build-dataset", help="Zbuduj zbiór twierdzeń z Google Fact Check Tools API.")
    build.add_argument("--size", type=int, default=DEFAULT_SIZE)
    build.add_argument("--seed", type=int, default=DEFAULT_SEED)
    build.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    build.add_argument("--out", type=Path, default=DEFAULT_DATASET)
    build.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED)
    build.set_defaults(handler=command_build_dataset)

    run = subcommands.add_parser("run", help="Wyślij zbiór do POST /api/check i policz mierniki z etykiet.")
    run.add_argument("--url", default=DEFAULT_BASE_URL)
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--out", type=Path, default=DEFAULT_RUNS)
    run.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    run.add_argument(
        "--limit", type=int, default=0, help="Tylko pierwsze N twierdzeń (próba przed pełnym przebiegiem)."
    )
    run.set_defaults(handler=command_run)

    judge = subcommands.add_parser("judge", help="Oceń odpowiedzi przebiegu sędzią LLM (Claude).")
    judge.add_argument("run_dir", type=Path)
    judge.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    judge.add_argument("--model", default=None, help="Model sędziego; domyślnie JUDGE_MODEL albo claude-opus-5-5.")
    judge.add_argument("--judge-repeats", type=int, default=DEFAULT_JUDGE_REPEATS)
    judge.set_defaults(handler=command_judge)

    report = subcommands.add_parser("report", help="Przelicz raport z zapisanych wyników i ocen sędziego.")
    report.add_argument("run_dir", type=Path)
    report.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    report.set_defaults(handler=command_report)

    compare = subcommands.add_parser("compare", help="Porównaj dwa przebiegi parami A/B i B/A sędzią LLM.")
    compare.add_argument("run_a", type=Path)
    compare.add_argument("run_b", type=Path)
    compare.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    compare.add_argument("--model", default=None)
    compare.add_argument("--out", type=Path, default=DEFAULT_RUNS)
    compare.set_defaults(handler=command_compare)

    compare_report = subcommands.add_parser("compare-report", help="Przelicz raport porównania z compare.json.")
    compare_report.add_argument("compare_dir", type=Path)
    compare_report.set_defaults(handler=command_compare_report)

    sample = subcommands.add_parser("human-sample", help="Wygeneruj human_review.csv do oceny przez ludzi.")
    sample.add_argument("run_dir", type=Path)
    sample.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sample.set_defaults(handler=command_human_sample)

    human_report = subcommands.add_parser("human-report", help="Policz wyniki ludzkie i zgodność z sędzią.")
    human_report.add_argument("run_dir", type=Path)
    human_report.set_defaults(handler=command_human_report)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
