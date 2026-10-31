"""Command line entry point: codeland-analyze REPO [-o city.json]."""

import argparse
import json
import sys
from pathlib import Path

from codeland_analyzer.build import analyze
from codeland_analyzer.native import DEFAULT_THRESHOLDS, NativeThresholds
from codeland_analyzer.sarif import SarifError
from codeland_analyzer.triage import TriageError, read_triage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codeland-analyze",
        description="Build the Codeland city model of a TypeScript git repository.",
    )
    parser.add_argument("repo", type=Path, help="path to the git repository")
    parser.add_argument("-o", "--output", type=Path, help="output JSON file (default: stdout)")
    parser.add_argument(
        "--churn-days", type=int, default=180, help="churn window in days (default: 180)"
    )
    parser.add_argument("--coverage", type=Path, help="LCOV report (e.g. coverage/lcov.info)")
    parser.add_argument(
        "--top", type=int, default=10, help="hotspots listed on stderr (default: 10, 0 = none)"
    )
    parser.add_argument(
        "--include-tests", action="store_true", help="also rank test files in the hotspot list"
    )
    parser.add_argument(
        "--previous",
        type=Path,
        help="earlier city model of the same repository; its layout is kept stable "
        "(may be the same file as --output)",
    )
    parser.add_argument(
        "--sarif",
        type=Path,
        action="append",
        default=[],
        help="SARIF 2.1.0 report to import as findings (repeatable)",
    )
    parser.add_argument(
        "--triage",
        type=Path,
        help="triage file with decisions about findings (managed with codeland-triage)",
    )
    parser.add_argument(
        "--no-native", action="store_true", help="skip Codeland's own maintainability findings"
    )
    defaults = DEFAULT_THRESHOLDS
    parser.add_argument(
        "--max-decisions",
        type=int,
        default=defaults.max_decisions,
        help=f"decisions in one file that count as a finding (default: {defaults.max_decisions})",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=defaults.min_coverage,
        help=f"coverage that flags a changing file (default: {defaults.min_coverage})",
    )
    args = parser.parse_args(argv)

    previous = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous else None
    native = None
    if not args.no_native:
        native = NativeThresholds(max_decisions=args.max_decisions, min_coverage=args.min_coverage)
    try:
        model = analyze(
            args.repo,
            churn_days=args.churn_days,
            coverage=args.coverage,
            previous=previous,
            sarif=args.sarif,
            native=native,
            triage=args.triage,
        )
    except (SarifError, TriageError) as error:
        print(f"codeland-analyze: {error}", file=sys.stderr)
        return 2
    text = json.dumps(model, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")

    buildings = model["buildings"]
    print(
        f"{len(buildings)} files, {len(model['districts'])} folders, {len(model['edges'])} imports",
        file=sys.stderr,
    )
    for source in model["analysis"]["findingSources"]:
        dropped = f", {source['dropped']} ignored" if source["dropped"] else ""
        print(f"  findings: {source['tool']} {source['findings']}{dropped}", file=sys.stderr)
    trend = model["analysis"]["trend"]
    if trend:
        since = trend["since"]
        added = sum(1 for f in model["findings"] if f["firstSeen"] > since)
        print(f"  trend since {since}: {added} new, {len(trend['fixed'])} fixed", file=sys.stderr)
    if args.triage:
        ids = {f["id"] for f in model["findings"]}
        entries = read_triage(args.triage)
        stale = sum(1 for key in entries if key not in ids)
        print(f"  triage: {len(entries) - stale} applied, {stale} stale", file=sys.stderr)
    if args.top > 0:
        ranked = sorted(
            (b for b in buildings if args.include_tests or b["role"] == "source"),
            key=lambda b: b["metrics"]["hotspot"],
            reverse=True,
        )
        for building in ranked[: args.top]:
            m = building["metrics"]
            if m["hotspot"] == 0:
                break
            coverage = "n/a" if m["coverage"] is None else f"{m['coverage']:.0%}"
            print(
                f"  {m['hotspot']:.2f}  {building['path']}  "
                f"({m['decisions']} decisions, {m['churnCommits']} commits, coverage {coverage})",
                file=sys.stderr,
            )
    return 0
