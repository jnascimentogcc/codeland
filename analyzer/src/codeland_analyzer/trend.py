"""Compares findings with the previous model: first-seen dates and what was fixed."""

from typing import Any

FIXED_LIMIT = 200


def apply_trend(
    findings: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    generated_at: str,
    tools: set[str],
) -> dict[str, Any] | None:
    """Sets `firstSeen` on every finding and returns the trend (None without a previous model).

    tools: tools that reported in this run; a previous finding of a tool that did not report now
    (report not supplied) is not counted as fixed.
    """
    old = {f["id"]: f for f in (previous or {}).get("findings", [])}
    since = (previous or {}).get("generatedAt")
    for finding in findings:
        known = old.get(finding["id"])
        finding["firstSeen"] = (known.get("firstSeen") or since) if known else generated_at
    if previous is None or since is None:
        return None
    now = {f["id"] for f in findings}
    gone = [f for f in old.values() if f["id"] not in now and f["source"]["tool"] in tools]
    gone.sort(key=lambda f: (f["location"]["path"], f["ruleId"], f["id"]))
    return {
        "since": since,
        "fixed": [
            {
                "id": f["id"],
                "ruleId": f["ruleId"],
                "title": f["title"],
                "category": f["category"],
                "severity": f["severity"],
                "path": f["location"]["path"],
            }
            for f in gone[:FIXED_LIMIT]
        ],
    }
