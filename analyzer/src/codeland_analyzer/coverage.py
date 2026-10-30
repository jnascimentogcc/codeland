"""Line coverage from LCOV reports (Jest, Vitest, c8, nyc)."""

from pathlib import Path


def read_lcov(report: Path, repo: Path) -> dict[str, float]:
    """Coverage ratio keyed by repository-relative path; files outside the repo are dropped."""
    result: dict[str, float] = {}
    path: str | None = None
    lines_found = lines_hit = da_found = da_hit = 0

    for line in report.read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            path = _repo_relative(line[3:], repo, report.parent)
            lines_found = lines_hit = da_found = da_hit = 0
        elif line.startswith("LF:"):
            lines_found = int(line[3:])
        elif line.startswith("LH:"):
            lines_hit = int(line[3:])
        elif line.startswith("DA:"):
            da_found += 1
            da_hit += int(line[3:].split(",")[1]) > 0
        elif line == "end_of_record":
            found, hit = (lines_found, lines_hit) if lines_found else (da_found, da_hit)
            if path is not None and found:
                result[path] = hit / found
            path = None
    return result


def _repo_relative(source: str, repo: Path, report_dir: Path) -> str | None:
    repo = repo.resolve()
    candidate = Path(source)
    bases = [candidate] if candidate.is_absolute() else [repo / candidate, report_dir / candidate]
    for base in bases:
        try:
            return base.resolve().relative_to(repo).as_posix()
        except ValueError:
            continue
    return None
