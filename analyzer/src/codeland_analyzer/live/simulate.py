"""Replays fake Claude Code hook payloads against codeland-live, for demos without real agents.

Two agents wander the city: each picks a file, reads it, sometimes edits it, runs a test now
and then, and both eventually edit the hottest file at the same time to trigger a conflict.
"""

import json
import random
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def simulate(
    repo: Path, city: Path, port: int, *, agents: int = 2, steps: int = 30, delay: float = 0.8
) -> None:
    model = json.loads(city.read_text(encoding="utf-8"))
    sources = [b for b in model["buildings"] if b["role"] == "source"]
    hottest = max(sources, key=lambda b: b["metrics"]["hotspot"])["path"]
    paths = [b["path"] for b in model["buildings"]]
    rng = random.Random(42)
    sessions = [str(uuid.UUID(int=rng.getrandbits(128))) for _ in range(agents)]
    url = f"http://127.0.0.1:{port}/events"
    repo = repo.resolve()

    def send(session: str, hook: str, **extra: Any) -> None:
        payload = {"session_id": session, "hook_event_name": hook, "cwd": str(repo), **extra}
        request = urllib.request.Request(
            url, json.dumps(payload).encode(), {"Content-Type": "application/json"}
        )
        urllib.request.urlopen(request, timeout=2).close()

    def tool(session: str, name: str, tool_input: dict[str, Any]) -> None:
        send(session, "PreToolUse", tool_name=name, tool_input=tool_input)
        time.sleep(delay / 2)
        send(session, "PostToolUse", tool_name=name, tool_input=tool_input, tool_response={})

    for session in sessions:
        send(session, "SessionStart", source="startup")
    for step in range(steps):
        session = sessions[step % agents]
        if step == steps - 4:  # every agent converges on the hottest file
            for s in sessions:
                send(
                    s, "PreToolUse", tool_name="Edit", tool_input={"file_path": str(repo / hottest)}
                )
            time.sleep(delay)
            continue
        path = rng.choice(paths)
        roll = rng.random()
        if roll < 0.15:
            tool(session, "Bash", {"command": "npm test", "description": "Run the test suite"})
        elif roll < 0.3:
            folder = str(repo / path.rpartition("/")[0])
            tool(session, "Grep", {"pattern": "export function", "path": folder})
        else:
            tool(session, "Read", {"file_path": str(repo / path)})
            if roll > 0.7:
                tool(session, "Edit", {"file_path": str(repo / path)})
        time.sleep(delay / 2)
    for session in sessions:
        send(session, "Stop")
