import { useEffect, useReducer, useState } from "react";
import type { CodelandLiveMessage } from "../model/agent-event";
import { applyMessage, EMPTY_LIVE_STATE, type LiveState } from "../model/agents";

export type LiveStatus = "off" | "connecting" | "live" | "offline";

const RECONNECT_MS = 2000;

/** ?live=<ws url> overrides the default ws://<host>:4317/ws; ?live=off disables. */
function liveUrl(): string | null {
  const param = new URLSearchParams(window.location.search).get("live");
  if (param === "off") return null;
  return param ?? `ws://${window.location.hostname || "localhost"}:4317/ws`;
}

/** Connects to codeland-live and keeps the agent state; reconnects while the server is down. */
export function useLive(): { state: LiveState; status: LiveStatus } {
  const [state, dispatch] = useReducer(applyMessage, EMPTY_LIVE_STATE);
  const [status, setStatus] = useState<LiveStatus>("connecting");

  useEffect(() => {
    const url = liveUrl();
    if (!url) {
      setStatus("off");
      return;
    }
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(url);
      socket.onopen = () => setStatus("live");
      socket.onmessage = (message) => {
        try {
          dispatch(JSON.parse(message.data as string) as CodelandLiveMessage);
        } catch {
          // Ignore malformed messages; the server only sends schema-shaped JSON.
        }
      };
      socket.onclose = () => {
        if (closed) return;
        setStatus("offline");
        retry = window.setTimeout(connect, RECONNECT_MS);
      };
    };
    connect();

    return () => {
      closed = true;
      window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  return { state, status };
}

/** Wall clock in seconds, re-rendering every `intervalMs` (drives conflict windows and fades). */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
