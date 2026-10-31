"""What an agent changed: file metrics before its first edit and after each edit.

The baseline is measured when the first edit of a file *starts* (PreToolUse runs before the tool,
and the hook's curl is synchronous), the result when an edit *ends*. Only line and decision counts
leave this module, never code.
"""

from pathlib import Path
from typing import Any

from codeland_analyzer.gitrepo import TS_SUFFIXES
from codeland_analyzer.parse import analyze_source

Snapshot = dict[str, int]
_MISSING: Snapshot = {}  # baseline marker: the file did not exist before the agent's first edit


class ChangeTracker:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._baselines: dict[tuple[str, str], Snapshot | None] = {}

    def track(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Change record for an edit event (null for anything else or non-TypeScript files)."""
        path = event.get("path")
        if event["kind"] != "edit" or not path or not path.endswith(TS_SUFFIXES):
            return None
        key = (event["agent"], path)
        if event["phase"] == "start":
            if key not in self._baselines:
                self._baselines[key] = self._measure(path) or _MISSING
            return None
        if key not in self._baselines:  # no PreToolUse seen (e.g. hooks installed mid-edit)
            return None
        before = self._baselines[key]
        return {"before": before or None, "after": self._measure(path)}

    def _measure(self, path: str) -> Snapshot | None:
        file = self.repo / path
        try:
            metrics = analyze_source(file.read_bytes(), tsx=path.endswith(".tsx"))
        except OSError:
            return None
        return {"loc": metrics.loc, "decisions": metrics.decisions}
