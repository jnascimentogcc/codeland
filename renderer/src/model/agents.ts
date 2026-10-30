// Pure reducer over live agent events (schema/agent-event.schema.json); no three.js here.
import type { AgentEvent, CodelandLiveMessage } from "./agent-event";

export const CONFLICT_WINDOW_SECONDS = 120;

export type AgentStatus = "active" | "idle" | "ended";

export interface AgentState {
  id: string;
  name: string;
  /** Hue in [0, 1), by order of appearance. */
  hue: number;
  status: AgentStatus;
  /** What the agent is working on: a file (read/edit), a folder (search), or null. */
  target: string | null;
  action: AgentEvent["kind"] | null;
  detail: string | null;
  reads: number;
  edits: number;
  commands: number;
  lastTs: number;
}

export interface FileActivity {
  agent: string;
  kind: "read" | "edit";
  ts: number;
}

export interface LiveState {
  repository: string | null;
  agents: Record<string, AgentState>;
  /** Agent ids in order of appearance. */
  order: string[];
  /** Latest read/edit per file path. */
  activity: Record<string, FileActivity>;
  /** path -> agent -> last edit time, for conflict detection. */
  edits: Record<string, Record<string, number>>;
}

export interface Conflict {
  path: string;
  agents: string[];
  ts: number;
}

export const EMPTY_LIVE_STATE: LiveState = {
  repository: null,
  agents: {},
  order: [],
  activity: {},
  edits: {},
};

export function agentHue(order: number): number {
  // Start at violet and step by the golden ratio, away from the debt layer's cyan-to-red ramp.
  return (0.78 + order * 0.618034) % 1;
}

export function applyMessage(state: LiveState, message: CodelandLiveMessage): LiveState {
  if (message.type === "snapshot") {
    return message.events.reduce(applyEvent, { ...EMPTY_LIVE_STATE, repository: message.repository });
  }
  return applyEvent(state, message);
}

export function applyEvent(state: LiveState, event: AgentEvent): LiveState {
  const known = state.agents[event.agent];
  const order = known ? state.order : [...state.order, event.agent];
  const agent: AgentState = known ?? {
    id: event.agent,
    name: `agente ${event.agent.slice(0, 4)}`,
    hue: agentHue(state.order.length),
    status: "active",
    target: null,
    action: null,
    detail: null,
    reads: 0,
    edits: 0,
    commands: 0,
    lastTs: event.ts,
  };
  const next: AgentState = { ...agent, lastTs: event.ts };
  let { activity, edits } = state;

  switch (event.kind) {
    case "session-start":
      next.status = "active";
      break;
    case "idle":
      next.status = "idle";
      next.action = null;
      next.detail = null;
      break;
    case "session-end":
      next.status = "ended";
      break;
    default:
      next.status = "active";
      next.action = event.kind;
      next.detail = event.detail;
      if (event.kind !== "command" && event.kind !== "other") next.target = event.path;
      if (event.phase === "end") {
        if (event.kind === "read") next.reads += 1;
        if (event.kind === "edit") next.edits += 1;
        if (event.kind === "command") next.commands += 1;
      }
      if ((event.kind === "read" || event.kind === "edit") && event.path) {
        // An edit keeps the stronger signal over a later read of the same file by the same agent.
        const previous = activity[event.path];
        const keepEdit =
          event.kind === "read" && previous?.kind === "edit" && previous.agent === event.agent;
        if (!keepEdit) {
          activity = { ...activity, [event.path]: { agent: event.agent, kind: event.kind, ts: event.ts } };
        }
      }
      if (event.kind === "edit" && event.path) {
        edits = { ...edits, [event.path]: { ...edits[event.path], [event.agent]: event.ts } };
      }
  }

  return { ...state, order, agents: { ...state.agents, [event.agent]: next }, activity, edits };
}

/** Files edited by two or more agents within the conflict window before `now`. */
export function conflicts(state: LiveState, now: number): Conflict[] {
  const result: Conflict[] = [];
  for (const [path, byAgent] of Object.entries(state.edits)) {
    const recent = Object.entries(byAgent).filter(
      ([id, ts]) => now - ts <= CONFLICT_WINDOW_SECONDS && state.agents[id]?.status !== "ended",
    );
    if (recent.length >= 2) {
      result.push({
        path,
        agents: recent.map(([id]) => id),
        ts: Math.max(...recent.map(([, ts]) => ts)),
      });
    }
  }
  return result.sort((a, b) => b.ts - a.ts);
}

export function visibleAgents(state: LiveState): AgentState[] {
  return state.order.map((id) => state.agents[id]!).filter((a) => a.status !== "ended");
}

export function describeAction(agent: AgentState): string {
  if (agent.status === "idle") return "aguardando";
  const target = agent.target ? ` ${agent.target || "/"}` : "";
  switch (agent.action) {
    case "read":
      return `lendo${target}`;
    case "edit":
      return `editando${target}`;
    case "search":
      return `buscando${agent.detail ? ` "${agent.detail}"` : ""}${target}`;
    case "command":
      return `executando ${agent.detail ?? "comando"}`;
    case null:
      return "iniciando";
    default:
      return agent.detail ?? "trabalhando";
  }
}
