"""Assembles the city model (schema/city-model.schema.json) from all analyzers."""

import posixpath
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codeland_analyzer import SCHEMA_VERSION
from codeland_analyzer.churn import Churn, collect_churn
from codeland_analyzer.coverage import read_lcov
from codeland_analyzer.gitrepo import head_info, is_test, list_source_files
from codeland_analyzer.layout import footprint_side, layout_city
from codeland_analyzer.parse import FileMetrics, analyze_source
from codeland_analyzer.resolve import is_relative, resolve

ROOT_DISTRICT_ID = "."


def district_id(path: str) -> str:
    return path or ROOT_DISTRICT_ID


def analyze(repo: Path, *, churn_days: int = 180, coverage: Path | None = None) -> dict[str, Any]:
    repo = repo.resolve()
    files = list_source_files(repo)
    known = set(files)
    parsed: dict[str, FileMetrics] = {
        path: analyze_source((repo / path).read_bytes(), tsx=path.endswith(".tsx"))
        for path in files
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
            target = resolve(path, ref.specifier, known)
            if target is None:
                (targets if is_relative(ref.specifier) else external).add(ref.specifier)
                continue
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
        {path: footprint_side(import_counts[path][0]) for path in files}
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

    commit, branch = head_info(repo)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "repository": {"name": repo.name, "commit": commit, "branch": branch},
        "analysis": {
            "language": "typescript",
            "churnWindowDays": churn_days,
            "coverageSource": coverage.as_posix() if coverage else None,
        },
        "districts": districts,
        "buildings": buildings,
        "edges": sorted(edges, key=lambda e: (e["from"], e["to"], e["kind"])),
    }
