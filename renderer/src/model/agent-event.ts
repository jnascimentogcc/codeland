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
  schemaVersion: "0.1.0";
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
   * start = PreToolUse, end = PostToolUse, status = lifecycle.
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
}
