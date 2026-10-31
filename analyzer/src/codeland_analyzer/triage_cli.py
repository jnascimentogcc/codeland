"""codeland-triage FILE accepted|false-positive|reopen ID... : edit the triage file."""

import argparse
import sys
from datetime import date
from pathlib import Path

from codeland_analyzer.triage import STATES, TriageError, read_triage, write_triage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codeland-triage",
        description="Record a decision about findings in a triage file (created when missing). "
        "Pass the file to codeland-analyze --triage to apply it.",
    )
    parser.add_argument("file", type=Path, help="triage file, e.g. codeland-triage.json")
    parser.add_argument(
        "state",
        choices=[*STATES, "reopen", "list"],
        help="accepted: known risk, left as is; false-positive: not a real problem; "
        "reopen: remove the decision",
    )
    parser.add_argument("ids", nargs="*", help="finding ids (shown in the finding card)")
    parser.add_argument("--note", help="why (kept in the file and shown in the finding card)")
    args = parser.parse_args(argv)

    try:
        entries = read_triage(args.file)
    except TriageError as error:
        print(f"codeland-triage: {error}", file=sys.stderr)
        return 2
    if args.state == "list":
        for key, entry in entries.items():
            print(f"{key}  {entry['state']}  {entry['note'] or ''}")
        return 0
    if not args.ids:
        print("codeland-triage: give at least one finding id", file=sys.stderr)
        return 2
    for key in args.ids:
        if args.state == "reopen":
            entries.pop(key, None)
        else:
            entries[key] = {"state": args.state, "note": args.note, "at": date.today().isoformat()}
    write_triage(args.file, entries)
    print(f"{args.file}: {len(entries)} decisions", file=sys.stderr)
    return 0
