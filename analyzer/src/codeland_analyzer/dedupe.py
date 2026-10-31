"""Marks findings that several tools report for the same place (docs 6.9)."""

from typing import Any

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_KIND_RANK = {"scanner": 0, "agent": 1, "native": 2}


def mark_duplicates(findings: list[dict[str, Any]]) -> None:
    """Sets `duplicateOf` on every finding: the id of the finding it repeats, or None.

    Two findings repeat each other when different tools report them in the same file and
    category on overlapping lines. Nothing is dropped. The more severe one (then scanner before
    agent before native, then tool name and id) stays primary; a finding is only ever marked
    against a primary, so a chain of overlaps cannot hide a finding no one else reported.
    """
    ranked = sorted(findings, key=_rank)
    primaries: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for finding in ranked:
        finding["duplicateOf"] = None
        start, end = _lines(finding)
        if start is None:
            primaries.setdefault(_key(finding), []).append(finding)
            continue
        group = primaries.setdefault(_key(finding), [])
        for other in group:
            other_start, other_end = _lines(other)
            if (
                other_start is not None
                and other["source"]["tool"] != finding["source"]["tool"]
                and start <= other_end  # type: ignore[operator]
                and other_start <= end  # type: ignore[operator]
            ):
                finding["duplicateOf"] = other["id"]
                break
        else:
            group.append(finding)


def _key(finding: dict[str, Any]) -> tuple[str, str]:
    return finding["location"]["path"], finding["category"]


def _lines(finding: dict[str, Any]) -> tuple[int | None, int | None]:
    start = finding["location"]["startLine"]
    return start, (finding["location"]["endLine"] or start)


def _rank(finding: dict[str, Any]) -> tuple[int, int, str, str]:
    source = finding["source"]
    return (
        _SEVERITY_RANK[finding["severity"]],
        _KIND_RANK[source["kind"]],
        source["tool"],
        finding["id"],
    )
