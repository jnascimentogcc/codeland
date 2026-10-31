"""Claude Code hook payload -> agent event (schema/agent-event.schema.json), minus seq and ts.

Only routing information survives: file contents, edit strings and tool responses are dropped,
and commands are reduced to a short label. The one thing read from a response is the verdict of
a test run (pass/fail and counts).
"""

import os
import re
from pathlib import Path
from typing import Any

_TOOL_KINDS = {
    "Read": "read",
    "Write": "edit",
    "Edit": "edit",
    "MultiEdit": "edit",
    "NotebookEdit": "edit",
    "Grep": "search",
    "Glob": "search",
    "Bash": "command",
}
_LIFECYCLE_KINDS = {"SessionStart": "session-start", "SessionEnd": "session-end", "Stop": "idle"}
_TOOL_PHASES = {"PreToolUse": "start", "PostToolUse": "end", "PostToolUseFailure": "end"}
_DETAIL_MAX = 80
_MSYS_DRIVE = re.compile(r"^/([a-zA-Z])(/|$)")  # Git Bash style /c/Users/...
_TEST_COMMAND = re.compile(
    r"\b(vitest|jest|pytest|mocha|ava|(npm|pnpm|yarn|bun)\s+(run\s+)?test|npm\s+t|go\s+test"
    r"|cargo\s+(test|nextest)|dotnet\s+test|playwright\s+test)\b"
)
_PASSED = re.compile(r"(\d+)\s+passed")
_FAILED = re.compile(r"(\d+)\s+failed")


def normalize(payload: dict[str, Any], repo: Path) -> dict[str, Any] | None:
    agent = payload.get("session_id")
    hook = payload.get("hook_event_name")
    if not isinstance(agent, str) or not agent:
        return None
    if hook in _LIFECYCLE_KINDS:
        return _event(agent, _LIFECYCLE_KINDS[hook], "status")
    if hook not in _TOOL_PHASES:
        return None

    tool = payload.get("tool_name")
    tool = tool if isinstance(tool, str) else None
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    kind = _TOOL_KINDS.get(tool or "", "other")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None

    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if kind == "search":
        target = tool_input.get("path") or cwd  # Grep/Glob default to the working directory
    path = repo_relative(target, repo, cwd) if isinstance(target, str) else None

    detail: str | None = None
    if kind == "command":
        detail = _short(tool_input.get("description") or tool_input.get("command"))
    elif kind == "search":
        detail = _short(tool_input.get("pattern"))
    phase = _TOOL_PHASES[hook]
    tests = None
    if kind == "command" and phase == "end":
        tests = _test_outcome(payload, tool_input, failed_hook=hook == "PostToolUseFailure")
    return _event(agent, kind, phase, path=path, tool=tool, detail=detail, tests=tests)


def _test_outcome(
    payload: dict[str, Any], tool_input: dict[str, Any], *, failed_hook: bool
) -> dict[str, Any] | None:
    """Pass/fail and counts of a finished test command; the output itself is never forwarded."""
    command = tool_input.get("command")
    if not isinstance(command, str) or not _TEST_COMMAND.search(command):
        return None
    output = _output_text(payload.get("tool_response")) + "\n" + _output_text(payload.get("error"))
    passed = _last_count(_PASSED, output)
    failed = _last_count(_FAILED, output)
    outcome = "fail" if failed_hook or failed else "pass"
    return {"outcome": outcome, "passed": passed, "failed": failed}


def _output_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(
            v for k in ("stdout", "stderr", "output") if isinstance(v := value.get(k), str)
        )
    return ""


def _last_count(pattern: re.Pattern[str], text: str) -> int | None:
    # Summaries come last (vitest prints "Test Files" before "Tests"), so the last match wins.
    matches = pattern.findall(text)
    return int(matches[-1]) if matches else None


def repo_relative(target: str, repo: Path, cwd: str | None = None) -> str | None:
    """Repository-relative posix path, "" for the root, None when outside the repository."""
    if os.name == "nt" and (match := _MSYS_DRIVE.match(target)):
        target = f"{match.group(1)}:/{target[match.end() :]}"
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = Path(cwd or repo) / candidate
    try:
        relative = candidate.resolve().relative_to(repo.resolve())
    except ValueError:
        return None
    text = relative.as_posix()
    return "" if text == "." else text


def _short(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    line = " ".join(value.split())
    return line if len(line) <= _DETAIL_MAX else line[: _DETAIL_MAX - 1] + "…"


def _event(
    agent: str,
    kind: str,
    phase: str,
    *,
    path: str | None = None,
    tool: str | None = None,
    detail: str | None = None,
    tests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "kind": kind,
        "phase": phase,
        "path": path,
        "tool": tool,
        "detail": detail,
        "tests": tests,
    }
