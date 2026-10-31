"""Assembles the city model (schema/city-model.schema.json) from all analyzers."""

import posixpath
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codeland_analyzer import SCHEMA_VERSION
from codeland_analyzer.churn import Churn, collect_churn
from codeland_analyzer.coverage import read_lcov
from codeland_analyzer.dedupe import mark_duplicates
from codeland_analyzer.gitrepo import (
    head_info,
    is_test,
    language_of,
    list_source_files,
    list_tsconfigs,
)
from codeland_analyzer.layout import footprint_side, layout_city, slots_from_model
from codeland_analyzer.native import DEFAULT_THRESHOLDS, SOURCE, NativeThresholds, native_findings
from codeland_analyzer.parse import FileMetrics, analyze_file
from codeland_analyzer.resolve import Resolver, load_tsconfigs
from codeland_analyzer.sarif import read_sarif
from codeland_analyzer.trend import apply_trend
from codeland_analyzer.triage import apply_triage, read_triage

ROOT_DISTRICT_ID = "."


def district_id(path: str) -> str:
    return path or ROOT_DISTRICT_ID


def analyze(
    repo: Path,
    *,
    churn_days: int = 180,
    coverage: Path | None = None,
    previous: dict[str, Any] | None = None,
    sarif: list[Path] | None = None,
    native: NativeThresholds | None = DEFAULT_THRESHOLDS,
    triage: Path | None = None,
) -> dict[str, Any]:
    """previous: an earlier city model of the same repository, whose layout is kept stable and
    whose findings give `firstSeen` and the trend.

    triage: sidecar file with human decisions about findings (see triage.py).

    sarif: SARIF 2.1.0 reports to import as findings; native: thresholds of Codeland's own
    findings (None to skip them).
    """
    repo = repo.resolve()
    files = list_source_files(repo)
    known = set(files)
    resolver = Resolver(known, load_tsconfigs(repo, list_tsconfigs(repo)))
    parsed: dict[str, FileMetrics] = {
        path: analyze_file(path, (repo / path).read_bytes()) for path in files
    }
    churn = collect_churn(repo, churn_days)
    coverage_by_file = read_lcov(coverage, repo) if coverage else {}

    edges: list[dict[str, str]] = []
    import_counts: dict[str, tuple[int, int]] = {}
    for path, metrics in parsed.items():
        targets: set[str] = set()
        external: set[str] = set()
        seen_edges: set[tuple[str, str]] = set()
        for ref in metrics.imports:
            resolved, relative = resolver.resolve(path, ref)
            if not resolved:
                (targets if relative else external).add(ref.specifier)
                continue
            for target in resolved:
                targets.add(target)
                if target != path and (target, ref.kind) not in seen_edges:
                    seen_edges.add((target, ref.kind))
                    edges.append({"from": path, "to": target, "kind": ref.kind})
        import_counts[path] = (len(targets) + len(external), len(external))

    # Decisions rather than complexity, so files with many trivial functions (test callbacks)
    # do not outrank files with real branching logic.
    max_decisions = max((m.decisions for m in parsed.values()), default=0) or 1
    max_commits = max((churn.get(p, Churn()).commits for p in files), default=0) or 1

    district_rects, building_rects = layout_city(
        {path: footprint_side(import_counts[path][0]) for path in files},
        slots_from_model(previous["districts"], previous["buildings"]) if previous else None,
    )

    buildings = []
    for path in files:
        metrics = parsed[path]
        file_churn = churn.get(path, Churn())
        imports, external_imports = import_counts[path]
        cov = coverage_by_file.get(path)
        hotspot = (metrics.decisions / max_decisions) * (file_churn.commits / max_commits)
        buildings.append(
            {
                "id": path,
                "path": path,
                "district": district_id(posixpath.dirname(path)),
                "role": "test" if is_test(path) else "source",
                "metrics": {
                    "loc": metrics.loc,
                    "complexity": metrics.complexity,
                    "decisions": metrics.decisions,
                    "maxFunctionComplexity": metrics.max_function_complexity,
                    "functions": metrics.functions,
                    "imports": imports,
                    "externalImports": external_imports,
                    "churnCommits": file_churn.commits,
                    "churnLines": file_churn.lines,
                    "coverage": None if cov is None else round(cov, 4),
                    "hotspot": round(hotspot, 4),
                },
                "layout": building_rects[path].to_json(),
            }
        )

    districts = [
        {
            "id": district_id(path),
            "path": path,
            "parent": None if not path else district_id(posixpath.dirname(path)),
            "depth": 0 if not path else path.count("/") + 1,
            "layout": rect.to_json(),
        }
        for path, rect in sorted(district_rects.items())
    ]

    findings, finding_sources = collect_findings(repo, buildings, sarif or [], native)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    trend = apply_trend(findings, previous, generated_at, {s["tool"] for s in finding_sources})
    if triage is not None:
        apply_triage(findings, read_triage(triage))
    commit, branch = head_info(repo)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "repository": {"name": repo.name, "commit": commit, "branch": branch},
        "analysis": {
            "languages": sorted({language_of(path) for path in files} - {None}),
            "churnWindowDays": churn_days,
            "coverageSource": coverage.as_posix() if coverage else None,
            "findingSources": finding_sources,
            "triageSource": triage.as_posix() if triage else None,
            "trend": trend,
        },
        "districts": districts,
        "buildings": buildings,
        "edges": sorted(edges, key=lambda e: (e["from"], e["to"], e["kind"])),
        "findings": findings,
    }


def collect_findings(
    repo: Path,
    buildings: list[dict[str, Any]],
    reports: list[Path],
    native: NativeThresholds | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for report in reports:
        imported = read_sarif(report, repo)
        findings.extend(imported.findings)
        sources.extend(imported.sources)
    if native is not None:
        own = native_findings(buildings, native)
        findings.extend(own)
        sources.append({**SOURCE, "file": None, "findings": len(own), "dropped": 0})
    findings.sort(
        key=lambda f: (
            f["location"]["path"],
            f["location"]["startLine"] or 0,
            f["ruleId"],
            f["id"],
        )
    )
    mark_duplicates(findings)
    return findings, sources
