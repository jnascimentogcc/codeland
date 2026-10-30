"""HTTP + WebSocket hub: hooks POST raw payloads to /events, clients listen on /ws."""

import logging
import time
from collections import deque
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from codeland_analyzer.live import EVENT_SCHEMA_VERSION
from codeland_analyzer.live.normalize import normalize

log = logging.getLogger("codeland.live")

HUB_KEY = web.AppKey("hub", "LiveHub")


class LiveHub:
    def __init__(self, repo: Path, history: int = 500) -> None:
        self.repo = repo.resolve()
        self.events: deque[dict[str, Any]] = deque(maxlen=history)
        self.clients: set[web.WebSocketResponse] = set()
        self._seq = 0

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        normalized = normalize(payload, self.repo)
        if normalized is None:
            return None
        self._seq += 1
        event = {"type": "agent-event", "seq": self._seq, "ts": time.time(), **normalized}
        self.events.append(event)
        return event

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "schemaVersion": EVENT_SCHEMA_VERSION,
            "repository": self.repo.name,
            "events": list(self.events),
        }

    async def broadcast(self, message: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except (ConnectionError, RuntimeError):
                self.clients.discard(ws)


async def _post_event(request: web.Request) -> web.Response:
    hub = request.app[HUB_KEY]
    try:
        payload = await request.json()
    except ValueError:
        return web.Response(status=400, text="expected a JSON hook payload")
    if not isinstance(payload, dict):
        return web.Response(status=400, text="expected a JSON object")
    event = hub.ingest(payload)
    if event is not None:
        log.info("%s %s %s %s", event["agent"][:8], event["kind"], event["phase"], event["path"])
        await hub.broadcast(event)
    return web.Response(status=204)


async def _websocket(request: web.Request) -> web.WebSocketResponse:
    hub = request.app[HUB_KEY]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    await ws.send_json(hub.snapshot())
    hub.clients.add(ws)
    try:
        async for message in ws:  # clients only listen; drain until they close
            if message.type == WSMsgType.ERROR:
                break
    finally:
        hub.clients.discard(ws)
    return ws


async def _health(request: web.Request) -> web.Response:
    hub = request.app[HUB_KEY]
    return web.json_response(
        {"repository": hub.repo.name, "clients": len(hub.clients), "events": len(hub.events)}
    )


def create_app(hub: LiveHub) -> web.Application:
    app = web.Application()
    app[HUB_KEY] = hub
    app.router.add_post("/events", _post_event)
    app.router.add_get("/ws", _websocket)
    app.router.add_get("/health", _health)
    return app


def serve(repo: Path, port: int, history: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    hub = LiveHub(repo, history)
    print(f"codeland-live: watching {hub.repo} on http://127.0.0.1:{port} (ws: /ws)")
    web.run_app(create_app(hub), host="127.0.0.1", port=port, print=None)
