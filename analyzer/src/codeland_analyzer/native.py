"""Codeland's own findings, derived from the metrics it already measures (docs section 6.4).

Deliberately few: scanners are better at everything else. Ids depend only on rule and path, so a
finding keeps its identity while its numbers change between scans.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

SOURCE = {"tool": "codeland", "version": None, "kind": "native"}


@dataclass(frozen=True)
class NativeThresholds:
    max_decisions: int = 25  # branching points in one file
    min_hotspot: float = 0.5  # normalized decisions x churn
    min_hotspot_decisions: int = (
        10  # hotspot is relative: the top file of a tiny repo is always 1.0
    )
    min_coverage: float = 0.5  # only for files that keep changing
    min_churn_commits: int = 2


DEFAULT_THRESHOLDS = NativeThresholds()


def native_findings(
    buildings: list[dict[str, Any]], thresholds: NativeThresholds
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for building in buildings:
        if building["role"] != "source":
            continue
        path, m = building["path"], building["metrics"]
        if m["decisions"] >= thresholds.max_decisions:
            severity = "high" if m["decisions"] >= 2 * thresholds.max_decisions else "medium"
            findings.append(
                _finding(
                    "codeland/high-complexity",
                    "Very high branching in one file",
                    "maintainability",
                    severity,
                    f"{m['decisions']} decision points in {m['loc']} lines "
                    f"(longest function complexity {m['maxFunctionComplexity']}).",
                    path,
                )
            )
        if (
            m["hotspot"] >= thresholds.min_hotspot
            and m["decisions"] >= thresholds.min_hotspot_decisions
        ):
            severity = "high" if m["hotspot"] >= 0.8 else "medium"
            findings.append(
                _finding(
                    "codeland/hotspot",
                    "Complex code that changes often",
                    "maintainability",
                    severity,
                    f"{m['decisions']} decision points and {m['churnCommits']} commits in the "
                    "churn window.",
                    path,
                )
            )
        coverage = m["coverage"]
        if (
            coverage is not None
            and coverage < thresholds.min_coverage
            and m["churnCommits"] >= thresholds.min_churn_commits
        ):
            findings.append(
                _finding(
                    "codeland/low-coverage",
                    "Low test coverage in code that changes",
                    "testing",
                    "medium",
                    f"{coverage:.0%} line coverage and {m['churnCommits']} commits in the "
                    "churn window.",
                    path,
                )
            )
    return findings


def _finding(
    rule_id: str, title: str, category: str, severity: str, message: str, path: str
) -> dict[str, Any]:
    digest = hashlib.sha256(f"codeland\x1f{rule_id}\x1f{path}".encode()).hexdigest()
    return {
        "id": digest[:16],
        "ruleId": rule_id,
        "title": title,
        "category": category,
        "severity": severity,
        "message": message,
        "location": {"path": path, "startLine": None, "endLine": None},
        "source": dict(SOURCE),
        "status": "open",
    }
