"""Change frequency per file over a time window, following renames."""

import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from codeland_analyzer.gitrepo import git

_BRACE_RENAME = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")


@dataclass
class Churn:
    commits: int = 0
    lines: int = 0


def collect_churn(repo: Path, days: int) -> dict[str, Churn]:
    """Churn keyed by the file's current path (history under older names is folded in)."""
    try:
        log = git(repo, "log", f"--since={days}.days", "-M", "--numstat", "--format=%x00%H")
    except subprocess.CalledProcessError:  # no commits yet
        return {}

    churn: dict[str, Churn] = defaultdict(Churn)
    current_name: dict[str, str] = {}  # older path -> current path
    # git log lists newest first, so a rename is seen before the older history of the file.
    for entry in log.split("\0")[1:]:
        touched: set[str] = set()
        for line in entry.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added, deleted, raw_path = parts
            old, new = split_rename(raw_path)
            path = current_name.get(new, new)
            if old != new:
                current_name[old] = path
            if added != "-":  # "-" marks binary files
                churn[path].lines += int(added) + int(deleted)
            touched.add(path)
        for path in touched:
            churn[path].commits += 1
    return dict(churn)


def split_rename(path: str) -> tuple[str, str]:
    """Parse numstat rename notation: "a => b" or "dir/{old => new}/file"."""
    if match := _BRACE_RENAME.match(path):
        prefix, old, new, suffix = match.groups()
        return _collapse(prefix + old + suffix), _collapse(prefix + new + suffix)
    if " => " in path:
        old, new = path.split(" => ", 1)
        return old, new
    return path, path


def _collapse(path: str) -> str:
    return re.sub(r"/+", "/", path)
