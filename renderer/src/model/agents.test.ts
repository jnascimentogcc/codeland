import { describe, expect, it } from "vitest";
import type { AgentEvent } from "./agent-event";
import {
  applyEvent,
  applyMessage,
  CONFLICT_WINDOW_SECONDS,
  conflicts,
  describeAction,
  describeTests,
  summarizeChanges,
  EMPTY_LIVE_STATE,
  visibleAgents,
} from "./agents";

let seq = 0;
function ev(agent: string, kind: AgentEvent["kind"], phase: AgentEvent["phase"], path: string | null, ts: number): AgentEvent {
  seq += 1;
  return { type: "agent-event", seq, ts, agent, kind, phase, path, tool: null, detail: null, tests: null, change: null };
}

const run = (...events: AgentEvent[]) => events.reduce(applyEvent, EMPTY_LIVE_STATE);

describe("applyEvent", () => {
  it("tracks agents in order of appearance with distinct hues", () => {
    const state = run(ev("aaaa-1", "session-start", "status", null, 1), ev("bbbb-2", "read", "start", "a.ts", 2));
    expect(state.order).toEqual(["aaaa-1", "bbbb-2"]);
    expect(state.agents["aaaa-1"]!.name).toBe("agente aaaa");
    expect(state.agents["aaaa-1"]!.hue).not.toBe(state.agents["bbbb-2"]!.hue);
  });

  it("moves the agent to its target and counts finished actions", () => {
    const state = run(
      ev("a", "read", "start", "src/x.ts", 1),
      ev("a", "read", "end", "src/x.ts", 2),
      ev("a", "edit", "start", "src/x.ts", 3),
      ev("a", "edit", "end", "src/x.ts", 4),
      ev("a", "command", "start", null, 5),
    );
    const agent = state.agents["a"]!;
    expect(agent.target).toBe("src/x.ts"); // commands keep the last file target
    expect([agent.reads, agent.edits, agent.commands]).toEqual([1, 1, 0]);
    expect(describeAction(agent)).toBe("executando comando");
    expect(state.activity["src/x.ts"]).toEqual({ agent: "a", kind: "edit", ts: 4 });
  });

  it("keeps an edit over a later read by the same agent", () => {
    const state = run(ev("a", "edit", "end", "x.ts", 1), ev("a", "read", "start", "x.ts", 2));
    expect(state.activity["x.ts"]!.kind).toBe("edit");
    const other = applyEvent(state, ev("b", "read", "start", "x.ts", 3));
    expect(other.activity["x.ts"]).toEqual({ agent: "b", kind: "read", ts: 3 });
  });

  it("marks idle and ended agents", () => {
    const state = run(ev("a", "read", "start", "x.ts", 1), ev("a", "idle", "status", null, 2), ev("b", "session-end", "status", null, 3));
    expect(describeAction(state.agents["a"]!)).toBe("aguardando");
    expect(visibleAgents(state).map((a) => a.id)).toEqual(["a"]);
  });
});

describe("test runs", () => {
  it("keeps the latest verdict of finished runs only", () => {
    const finished = (outcome: "pass" | "fail", passed: number | null, failed: number | null, ts: number) => ({
      ...ev("a", "command", "end", null, ts),
      tests: { outcome, passed, failed },
    });
    const started = { ...ev("a", "command", "start", null, 1), tests: null };
    expect(run(started).agents["a"]!.tests).toBeNull();

    const failing = run(started, finished("fail", 10, 2, 2));
    expect(failing.agents["a"]!.tests).toEqual({ outcome: "fail", passed: 10, failed: 2, ts: 2 });
    expect(describeTests(failing.agents["a"]!.tests!)).toBe("10 ok · 2 falhas");

    const fixed = applyEvent(failing, finished("pass", 12, 0, 3));
    expect(fixed.agents["a"]!.tests!.outcome).toBe("pass");
    // A command that is not a test run does not erase the verdict.
    expect(applyEvent(fixed, ev("a", "command", "end", null, 4)).agents["a"]!.tests!.ts).toBe(3);
  });

  it("describes verdicts without counts", () => {
    expect(describeTests({ outcome: "fail", passed: null, failed: null })).toBe("testes falharam");
    expect(describeTests({ outcome: "pass", passed: null, failed: null })).toBe("testes passaram");
    expect(describeTests({ outcome: "fail", passed: null, failed: 1 })).toBe("1 falha");
  });
});

describe("changes", () => {
  const size = (loc: number, decisions: number) => ({ loc, decisions });
  const edited = (path: string, before: ReturnType<typeof size> | null, after: ReturnType<typeof size> | null, ts: number) => ({
    ...ev("a", "edit", "end", path, ts),
    change: { before, after },
  });

  it("keeps the first baseline and the latest result per file", () => {
    const state = run(
      edited("x.ts", size(100, 10), size(110, 14), 1),
      edited("x.ts", size(110, 14), size(120, 18), 2),
      edited("y.ts", null, size(30, 2), 3),
      edited("z.ts", size(50, 5), size(50, 5), 4),
    );
    const summary = summarizeChanges(state.agents["a"]!);
    expect(summary.files).toEqual([
      { path: "x.ts", loc: 20, decisions: 8, created: false, deleted: false },
      { path: "y.ts", loc: 30, decisions: 2, created: true, deleted: false },
    ]);
    expect([summary.loc, summary.decisions]).toEqual([50, 10]);
  });

  it("reports debt paid down as negative decisions", () => {
    const state = run(edited("x.ts", size(200, 30), size(150, 12), 1), edited("x.ts", size(150, 12), null, 2));
    const [file] = summarizeChanges(state.agents["a"]!).files;
    expect(file).toMatchObject({ loc: -200, decisions: -30, deleted: true });
  });
});

describe("conflicts", () => {
  it("reports files edited by two agents within the window", () => {
    const state = run(ev("a", "edit", "start", "x.ts", 100), ev("b", "edit", "start", "x.ts", 150), ev("b", "edit", "start", "y.ts", 150));
    expect(conflicts(state, 160)).toEqual([{ path: "x.ts", agents: ["a", "b"], ts: 150 }]);
    expect(conflicts(state, 100 + CONFLICT_WINDOW_SECONDS + 1)).toEqual([]);
  });

  it("ignores agents whose session ended", () => {
    const state = run(ev("a", "edit", "start", "x.ts", 1), ev("b", "edit", "start", "x.ts", 2), ev("a", "session-end", "status", null, 3));
    expect(conflicts(state, 4)).toEqual([]);
  });
});

describe("applyMessage", () => {
  it("rebuilds the state from a snapshot", () => {
    const stale = run(ev("old", "read", "start", "z.ts", 1));
    const state = applyMessage(stale, {
      type: "snapshot",
      schemaVersion: "0.3.0",
      repository: "bella-nina",
      events: [ev("a", "read", "start", "x.ts", 5)],
    });
    expect(state.repository).toBe("bella-nina");
    expect(state.order).toEqual(["a"]);
  });
});
