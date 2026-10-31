"""codeland-sweep REPO --kind security: an agent reviews the code and the city is re-analyzed."""

import argparse
import json
import sys
from pathlib import Path

from codeland_analyzer.build import analyze
from codeland_analyzer.sarif import SarifError
from codeland_analyzer.sweep import DEFAULT_MODEL, KINDS, SweepError, sweep
from codeland_analyzer.triage import TriageError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codeland-sweep",
        description="Run a read-only Claude Code session over a TypeScript repository, save its "
        "findings as SARIF (sweep agent contract, docs 6.8) and optionally re-analyze the city.",
    )
    parser.add_argument("repo", type=Path, help="path to the git repository")
    parser.add_argument("--kind", choices=list(KINDS), default="security", help="what to review")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="SARIF file to write (default: codeland-sweep-<kind>.sarif in the current folder)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"default: {DEFAULT_MODEL}")
    parser.add_argument(
        "--budget", type=float, default=2.0, help="spending cap in USD for the session (default: 2)"
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="only review files under this repository-relative prefix (repeatable)",
    )
    parser.add_argument(
        "--city",
        type=Path,
        help="city model to re-analyze with the new findings; an existing file is the --previous "
        "model (trend and stable layout) and is overwritten",
    )
    parser.add_argument(
        "--sarif",
        type=Path,
        action="append",
        default=[],
        help="other SARIF reports to import together with the sweep when re-analyzing",
    )
    parser.add_argument("--triage", type=Path, help="triage file to apply when re-analyzing")
    args = parser.parse_args(argv)

    output = args.output or Path(f"codeland-sweep-{args.kind}.sarif")
    try:
        print(f"sweeping {args.repo} for {args.kind} with {args.model}...", file=sys.stderr)
        report = sweep(
            args.repo, args.kind, model=args.model, budget=args.budget, paths=args.path or None
        )
        output.write_text(json.dumps(report.document, indent=2) + "\n", encoding="utf-8")
        print(f"{output}: {report.results} findings", file=sys.stderr)
        if report.dropped:
            print(
                f"  {report.dropped} results dropped (outside scope or over the cap)",
                file=sys.stderr,
            )
        for note in report.notes:
            print(f"  {note}", file=sys.stderr)
        if args.city:
            previous = None
            if args.city.exists():
                previous = json.loads(args.city.read_text(encoding="utf-8"))
            model = analyze(
                args.repo,
                previous=previous,
                sarif=[*args.sarif, output],
                triage=args.triage,
            )
            args.city.write_text(
                json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            trend = model["analysis"]["trend"]
            extra = ""
            if trend:
                added = sum(1 for f in model["findings"] if f["firstSeen"] > trend["since"])
                extra = f" ({added} new, {len(trend['fixed'])} fixed since {trend['since']})"
            print(f"{args.city}: {len(model['findings'])} findings{extra}", file=sys.stderr)
    except (SweepError, SarifError, TriageError) as error:
        print(f"codeland-sweep: {error}", file=sys.stderr)
        return 2
    return 0
