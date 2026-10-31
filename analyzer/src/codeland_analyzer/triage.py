"""Human decisions about findings, kept in a sidecar file keyed by finding id (docs 6.7)."""

import json
from pathlib import Path
from typing import Any

STATES = ("accepted", "false-positive")
VERSION = 1


class TriageError(Exception):
    pass


def read_triage(path: Path) -> dict[str, dict[str, Any]]:
    """{finding id: {state, note, at}}; a missing file is an empty triage."""
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        entries = document["findings"]
        if document.get("version") != VERSION or not isinstance(entries, dict):
            raise ValueError("unsupported version")
        for entry in entries.values():
            if entry["state"] not in STATES:
                raise ValueError(f"unknown state {entry['state']!r}")
    except (ValueError, KeyError, TypeError) as error:
        raise TriageError(f"{path}: not a Codeland triage file ({error})") from error
    return {
        key: {"state": e["state"], "note": e.get("note"), "at": e.get("at")}
        for key, e in entries.items()
    }


def write_triage(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    document = {"version": VERSION, "findings": dict(sorted(entries.items()))}
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def apply_triage(findings: list[dict[str, Any]], entries: dict[str, dict[str, Any]]) -> list[str]:
    """Attaches `triage` to the matching findings; returns the ids that match nothing (stale)."""
    by_id = {f["id"]: f for f in findings}
    for key, entry in entries.items():
        if key in by_id:
            by_id[key]["triage"] = dict(entry)
    return sorted(set(entries) - set(by_id))
