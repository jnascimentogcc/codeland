import json
import os
from pathlib import Path

import jsonschema
import pytest

from codeland_analyzer.live import hooks
from codeland_analyzer.live.changes import ChangeTracker
from codeland_analyzer.live.normalize import normalize, repo_relative
from codeland_analyzer.live.server import LiveHub, create_app

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "schema" / "agent-event.schema.json").read_text(encoding="utf-8")
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    return root


def hook(name: str, **extra) -> dict:
    return {"session_id": "s-1", "hook_event_name": name, **extra}


def test_tool_events_keep_only_routing_information(repo):
    secret = "const API_KEY = 'do-not-forward';"
    event = normalize(
        hook(
            "PostToolUse",
            cwd=str(repo),
            tool_name="Write",
            tool_input={"file_path": str(repo / "src" / "a.ts"), "content": secret},
            tool_response={"filePath": str(repo / "src" / "a.ts"), "content": secret},
        ),
        repo,
    )

    assert event == {
        "agent": "s-1",
        "kind": "edit",
        "phase": "end",
        "path": "src/a.ts",
        "tool": "Write",
        "detail": None,
        "tests": None,
    }
    assert "do-not-forward" not in json.dumps(event)


@pytest.mark.parametrize(
    ("tool", "tool_input", "kind", "path", "detail"),
    [
        ("Read", {"file_path": "src/b.ts"}, "read", "src/b.ts", None),  # relative to cwd
        ("Grep", {"pattern": "export"}, "search", "", "export"),  # defaults to cwd = root
        ("Glob", {"pattern": "**/*.ts", "path": "src"}, "search", "src", "**/*.ts"),
        ("Bash", {"command": "npm test", "description": "Run tests"}, "command", None, "Run tests"),
        ("TodoWrite", {"todos": []}, "other", None, None),
    ],
)
def test_tool_kinds(repo, tool, tool_input, kind, path, detail):
    event = normalize(
        hook("PreToolUse", cwd=str(repo), tool_name=tool, tool_input=tool_input), repo
    )

    assert event is not None
    assert (event["kind"], event["phase"], event["path"], event["detail"]) == (
        kind,
        "start",
        path,
        detail,
    )


def test_long_commands_are_shortened(repo):
    event = normalize(
        hook("PreToolUse", tool_name="Bash", tool_input={"command": "echo " + "x" * 200}), repo
    )
    assert event is not None and len(event["detail"]) == 80 and event["detail"].endswith("…")


def bash_end(repo, command, hook_name="PostToolUse", **extra):
    payload = hook(hook_name, tool_name="Bash", tool_input={"command": command}, **extra)
    return normalize(payload, repo)


def test_test_runs_report_a_verdict_and_counts_but_no_output(repo):
    vitest = "Test Files  1 failed | 2 passed (3)\n      Tests  2 failed | 10 passed (12)\n"
    failed = bash_end(
        repo, "npx vitest run", "PostToolUseFailure", error=f"Exit code 1\n{vitest}secret-log"
    )
    assert failed["tests"] == {"outcome": "fail", "passed": 10, "failed": 2}
    assert "secret-log" not in json.dumps(failed)

    pytest_out = {"stdout": "===== 7 passed in 0.4s =====", "stderr": ""}
    passed = bash_end(repo, "uv run pytest -q", tool_response=pytest_out)
    assert passed["tests"] == {"outcome": "pass", "passed": 7, "failed": None}

    # A failing exit without a parsable summary is still a failure.
    crashed = bash_end(repo, "npm test", "PostToolUseFailure", error="Exit code 1")
    assert crashed["tests"] == {"outcome": "fail", "passed": None, "failed": None}


def test_only_finished_test_commands_get_a_verdict(repo):
    assert bash_end(repo, "ls src", tool_response={"stdout": "5 passed"})["tests"] is None
    start = normalize(
        hook("PreToolUse", tool_name="Bash", tool_input={"command": "npm test"}), repo
    )
    assert start["tests"] is None


def test_lifecycle_and_unknown_hooks(repo):
    assert normalize(hook("SessionStart"), repo)["kind"] == "session-start"
    assert normalize(hook("Stop"), repo)["kind"] == "idle"
    assert normalize(hook("SessionEnd"), repo)["phase"] == "status"
    assert normalize(hook("Notification"), repo) is None
    assert normalize({"hook_event_name": "Stop"}, repo) is None


def test_paths_outside_the_repository_are_dropped(repo, tmp_path):
    assert repo_relative(str(tmp_path / "elsewhere.ts"), repo) is None
    assert repo_relative(str(repo), repo) == ""


@pytest.mark.skipif(os.name != "nt", reason="Git Bash drive paths only exist on Windows")
def test_git_bash_drive_paths(repo):
    resolved = repo.resolve()
    msys = "/" + resolved.drive[0].lower() + resolved.as_posix()[2:] + "/src/a.ts"
    assert repo_relative(msys, repo) == "src/a.ts"


def test_install_hooks_is_idempotent_and_keeps_other_hooks(repo):
    settings = hooks.settings_path(repo)
    settings.parent.mkdir()
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
    settings.write_text(json.dumps({"permissions": {}, "hooks": {"PreToolUse": [other]}}))

    hooks.install(repo, 4317)
    hooks.install(repo, 5000)
    installed = json.loads(settings.read_text())

    assert installed["permissions"] == {}
    assert installed["hooks"]["PreToolUse"][0] == other
    ours = [
        h["command"]
        for entries in installed["hooks"].values()
        for entry in entries
        for h in entry["hooks"]
        if hooks.MARKER in h["command"]
    ]
    assert len(ours) == 6 and all(":5000/events" in c for c in ours)

    hooks.uninstall(repo)
    assert json.loads(settings.read_text()) == {
        "permissions": {},
        "hooks": {"PreToolUse": [other]},
    }


async def test_server_broadcasts_normalized_events(repo, aiohttp_client):
    client = await aiohttp_client(create_app(LiveHub(repo)))
    first = hook("PreToolUse", cwd=str(repo), tool_name="Read", tool_input={"file_path": "a.ts"})
    assert (await client.post("/events", json=first)).status == 204

    ws = await client.ws_connect("/ws")
    snapshot = await ws.receive_json()
    jsonschema.validate(snapshot, SCHEMA)
    assert [e["path"] for e in snapshot["events"]] == ["a.ts"]

    second = hook("PostToolUse", cwd=str(repo), tool_name="Edit", tool_input={"file_path": "b.ts"})
    assert (await client.post("/events", json=second)).status == 204
    live = await ws.receive_json()
    jsonschema.validate(live, SCHEMA)
    assert (live["seq"], live["kind"], live["path"]) == (2, "edit", "b.ts")

    assert (await client.post("/events", data="not json")).status == 400
    assert (await client.get("/health")).status == 200
    await ws.close()


def edit_event(agent: str, phase: str, path: str) -> dict:
    return {"agent": agent, "kind": "edit", "phase": phase, "path": path}


def test_changes_measure_before_the_first_edit_and_after_each_edit(repo):
    tracker = ChangeTracker(repo)
    file = repo / "src" / "a.ts"
    file.write_text("export function f(x: number) {\n  return x;\n}\n")

    assert tracker.track(edit_event("s-1", "start", "src/a.ts")) is None
    file.write_text(
        "export function f(x: number) {\n  if (x) {\n    return 1;\n  }\n  return x;\n}\n"
    )
    first = tracker.track(edit_event("s-1", "end", "src/a.ts"))
    assert first == {"before": {"loc": 3, "decisions": 0}, "after": {"loc": 6, "decisions": 1}}

    # A second edit keeps the session baseline; another agent gets its own.
    tracker.track(edit_event("s-1", "start", "src/a.ts"))
    file.write_text("export const f = 1;\n")
    second = tracker.track(edit_event("s-1", "end", "src/a.ts"))
    assert second["before"] == {"loc": 3, "decisions": 0}
    assert second["after"] == {"loc": 1, "decisions": 0}
    tracker.track(edit_event("s-2", "start", "src/a.ts"))
    third = tracker.track(edit_event("s-2", "end", "src/a.ts"))
    assert third["before"] == third["after"] == {"loc": 1, "decisions": 0}


def test_changes_for_new_deleted_and_ignored_files(repo):
    tracker = ChangeTracker(repo)
    new = repo / "src" / "new.ts"
    tracker.track(edit_event("s-1", "start", "src/new.ts"))
    new.write_text("export const a = 1;\n")
    created = tracker.track(edit_event("s-1", "end", "src/new.ts"))
    assert created == {"before": None, "after": {"loc": 1, "decisions": 0}}

    new.unlink()
    tracker.track(edit_event("s-2", "start", "src/new.ts"))  # baseline already gone elsewhere
    assert tracker.track(edit_event("s-1", "end", "src/new.ts"))["after"] is None

    assert tracker.track(edit_event("s-1", "start", "README.md")) is None
    assert tracker.track(edit_event("s-1", "end", "README.md")) is None
    assert tracker.track(edit_event("s-3", "end", "src/new.ts")) is None  # never saw the start
    assert tracker.track({"agent": "s-1", "kind": "read", "phase": "end", "path": "a.ts"}) is None
