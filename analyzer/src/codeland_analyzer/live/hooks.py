"""Installs Claude Code hooks that forward every hook payload to codeland-live.

Hooks go to <repo>/.claude/settings.local.json (personal, normally git-ignored). The command is a
curl with a 1 s timeout that always exits 0, so a stopped server never slows or blocks the agent.
Our entries are recognized by a marker comment, so install is idempotent and uninstall leaves
other hooks alone.
"""

import json
from pathlib import Path
from typing import Any

MARKER = "# codeland-live"
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure")  # failure = non-zero exit
LIFECYCLE_EVENTS = ("SessionStart", "Stop", "SessionEnd")


def settings_path(repo: Path) -> Path:
    return repo / ".claude" / "settings.local.json"


def hook_command(port: int) -> str:
    return (
        'curl -s -m 1 -o /dev/null -H "Content-Type: application/json" '
        f"--data-binary @- http://127.0.0.1:{port}/events || true {MARKER}"
    )


def install(repo: Path, port: int) -> Path:
    path = settings_path(repo)
    settings = _load(path)
    _remove_ours(settings)
    hooks = settings.setdefault("hooks", {})
    handler = {"type": "command", "command": hook_command(port), "timeout": 3}
    for event in TOOL_EVENTS:
        hooks.setdefault(event, []).append({"matcher": "*", "hooks": [dict(handler)]})
    for event in LIFECYCLE_EVENTS:
        hooks.setdefault(event, []).append({"hooks": [dict(handler)]})
    _save(path, settings)
    return path


def uninstall(repo: Path) -> Path:
    path = settings_path(repo)
    settings = _load(path)
    _remove_ours(settings)
    _save(path, settings)
    return path


def _remove_ours(settings: dict[str, Any]) -> None:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        entries = [
            entry
            for entry in hooks[event]
            if not any(MARKER in h.get("command", "") for h in entry.get("hooks", []))
        ]
        if entries:
            hooks[event] = entries
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8") or "{}")


def _save(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
