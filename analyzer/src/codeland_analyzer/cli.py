"""Command line entry point: codeland-analyze REPO [-o city.json]."""

import argparse
import json
import sys
from pathlib import Path

from codeland_analyzer.build import analyze


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
    args = parser.parse_args(argv)

    model = analyze(args.repo, churn_days=args.churn_days, coverage=args.coverage)
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
