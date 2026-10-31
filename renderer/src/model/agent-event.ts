/* Generated from schema/agent-event.schema.json by npm run gen:types. Do not edit. */

/**
 * Messages the live server (codeland-live) sends to clients over its WebSocket. Raw hook payloads are normalized server-side; file contents, diffs and command output are never forwarded.
 */
export type CodelandLiveMessage = Snapshot | AgentEvent;

/**
 * First message on every connection: recent history, oldest first.
 */
export interface Snapshot {
  type: "snapshot";
  schemaVersion: "0.3.0";
  /**
   * Name of the observed repository folder.
   */
  repository: string;
  events: AgentEvent[];
}
export interface AgentEvent {
  type: "agent-event";
  /**
   * Monotonic per server run.
   */
  seq: number;
  /**
   * Unix time in seconds.
   */
  ts: number;
  /**
   * Claude Code session id.
   */
  agent: string;
  /**
   * edit covers Write, Edit, MultiEdit and NotebookEdit; search covers Grep and Glob.
   */
  kind: "session-start" | "session-end" | "idle" | "read" | "edit" | "search" | "command" | "other";
  /**
   * start = PreToolUse, end = PostToolUse or PostToolUseFailure, status = lifecycle.
   */
  phase: "start" | "end" | "status";
  /**
   * Repository-relative target with forward slashes: a file for read/edit, a folder for search ("" = root); null when outside the repository or not applicable.
   */
  path: string | null;
  tool: string | null;
  /**
   * Short human label (e.g. the Bash description or a truncated command).
   */
  detail: string | null;
  /**
   * Verdict of a finished test command (vitest, jest, pytest, npm test, ...); null for every other event. Only the verdict and counts are forwarded, never the output.
   */
  tests: null | TestRun;
  /**
   * Effect of a finished edit of a TypeScript file, measured on disk: metrics before the agent's first edit of that file and now. Null for every other event.
   */
  change: null | FileChange;
}
export interface TestRun {
  /**
   * fail when the command exited non-zero or reported failed tests.
   */
  outcome: "pass" | "fail";
  /**
   * Passed tests when the summary could be parsed.
   */
  passed: number | null;
  /**
   * Failed tests when the summary could be parsed.
   */
  failed: number | null;
}
export interface FileChange {
  /**
   * Null when the agent created the file.
   */
  before: null | FileSize;
  /**
   * Null when the file no longer exists.
   */
  after: null | FileSize;
}
export interface FileSize {
  loc: number;
  /**
   * Branching points (complexity minus one per function).
   */
  decisions: number;
}
