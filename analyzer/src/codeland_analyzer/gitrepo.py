"""Thin wrapper around the git CLI: source file discovery and HEAD information."""

import subprocess
from pathlib import Path

TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
_DECLARATION_SUFFIXES = (".d.ts", ".d.mts", ".d.cts")
_TEST_FOLDERS = frozenset({"test", "tests", "__tests__"})
_TEST_MARKERS = (".test.", ".spec.")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotepath=off", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def is_source(path: str) -> bool:
    return path.endswith(TS_SUFFIXES) and not path.endswith(_DECLARATION_SUFFIXES)


def is_test(path: str) -> bool:
    *folders, name = path.split("/")
    return any(marker in name for marker in _TEST_MARKERS) or not _TEST_FOLDERS.isdisjoint(folders)


def list_source_files(repo: Path) -> list[str]:
    """Tracked and untracked-but-not-ignored TypeScript files (so node_modules etc. are skipped)."""
    out = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    paths = {p for p in out.split("\0") if p and is_source(p)}
    return sorted(p for p in paths if (repo / p).is_file())


def head_info(repo: Path) -> tuple[str | None, str | None]:
    """(commit SHA, branch name); None for each when unborn or detached."""
    try:
        commit = git(repo, "rev-parse", "HEAD").strip()
    except subprocess.CalledProcessError:
        return None, None
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return commit, None if branch == "HEAD" else branch


def file_hashes(repo: Path, paths: list[str]) -> dict[str, str]:
    """Git blob hash of each file's current content (working tree, committed or not)."""
    if not paths:
        return {}
    out = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "--stdin-paths"],
        input="\n".join(paths) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return dict(zip(paths, out.split(), strict=True))
