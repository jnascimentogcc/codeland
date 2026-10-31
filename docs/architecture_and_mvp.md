# Codeland – Architecture Considerations and MVP Plan

This document builds on the initial vision in [codeland_concept.md](codeland_concept.md). It records the open decisions, the proposed architecture and a phased plan for a first usable version. It is a working document: decisions marked **Open** still need an owner and an answer.

---

## 0. Direction change: findings dashboard — **Decided**

Phases 1 and 2 (sections 4.1 and 4.2) showed that the real-time agent view is fun but has little day-to-day use. The project pivots to a **code problems dashboard**: a static, repeatable representation of what is wrong in a codebase and what to fix first. Section 6 holds the decisions; where it conflicts with sections 1, 2.1 and 4, section 6 wins.

* **Primary use case:** *"What problems does this code have, where are they, and which should I fix first?"* Technical debt is one category of problem among others (security, reliability, tests, dependencies, ...), not the whole product.
* **The city is the map, not the whole dashboard.** It answers *where* and *what first*; a 2D panel (counts, filters, ordered list) is where work happens.
* **Findings come from scanners, not from Codeland.** The input format is **SARIF 2.1.0**, the standard output of Semgrep, CodeQL, ESLint, Trivy, Gitleaks and many others. Codeland adds its own native maintainability findings from what it already measures.
* **Agents move to the future:** sweep agents (security, but not limited to it) will be one more *producer* of findings, writing SARIF. The live agent view (4.2) is kept in the repository but is not part of the new product surface for now.

---

## 1. Positioning

### 1.1 Prior art
Software cities are an established visualization technique, which lowers the conceptual risk and gives reference material:

* **CodeCity** (Wettel & Lanza, ~2008): packages as districts, classes as buildings; height/footprint driven by metrics. Studies showed it is effective for overview and for locating anomalies, less so for fine-grained tasks.
* **CodeCharta**: city maps from static analysis, with layout and metric selection.
* **Gource**: animated git history (time dimension, but not a city).

### 1.2 Differentiation
The static city alone is not new. Codeland's value is in combining in one scene:

1. **Time** – git history playback over a stable city.
2. **Life** – CI/CD and runtime events as visible activity.
3. **AI agents** – observing (and steering) multiple autonomous agents working on the same repository. This is the most current and least served need, and should be treated as a primary use case, not a decorative feature.

---

## 2. Open Decisions

### 2.1 Target user and core questions — **Decided**
The concept describes what is seen, not who looks and why. Each candidate leads to a different product:

| Candidate use case | Key question the city must answer |
|---|---|
| Onboarding | "How is this system organized and where do I start?" |
| Technical debt prioritization | "Where is complexity and churn concentrated?" |
| Incident triage | "What changed recently near the failing area?" |
| AI agent oversight | "What are the agents doing right now, and where?" |

**Decision:** the two primary use cases are **technical debt prioritization** and **AI agent oversight**. Onboarding and incident triage are secondary: they benefit from the same city but do not drive design decisions.

Core questions for each primary use case:

* **Technical debt prioritization**
  * Where are the hotspots, i.e. code that is both complex and frequently changed (complexity × churn)?
  * Which hotspots lack test coverage?
  * Is debt growing or shrinking over time, and in which districts?
* **AI agent oversight**
  * Which agents are active right now, and which buildings are they touching?
  * Are two agents (or an agent and a human) working on the same area, at risk of conflict?
  * What did an agent change in its session, and did the tests pass?

**Where the two meet:** the same metrics serve both. The city can show whether agents are *reducing* debt (refactoring hotspots) or *introducing* it (adding complexity, lowering coverage). It can also guide them, by giving agents the hotspot list as refactoring targets through the MCP server (3.3). This combination is Codeland's main differentiator and should shape the roadmap.

### 2.2 Visual encoding — **Open**
The concept overloads visual channels (glow, sparks and flashing lights are used for coverage, failures, conflicts, IDE presence, audits and deploys) and leaves some mappings ambiguous:

* **Height** = "LOC *or* cyclomatic complexity" → choose one default.
* **Footprint** = "coupling" → afferent (who depends on me) and efferent (whom I depend on) mean opposite things; choose one.
* **Material** = "clean vs legacy" → needs a measurable definition (age, churn, smells, duplication).

**Rule:** one metric per channel per layer. Users switch between **layers** (like map filters) instead of seeing everything at once.

Proposed default encoding:

| Channel | Base layer (structure) | Debt layer | Agents layer |
|---|---|---|---|
| Height | LOC | LOC | LOC |
| Footprint | Efferent coupling (imports) | Efferent coupling | Efferent coupling |
| Color | Language / module | Hotspot score: complexity × churn (sequential scale) | Agent that last touched the file (categorical, one color per agent) |
| Material | Neutral | Code age (concrete/rust for old, untouched complex code) | Neutral |
| Glow / emission | — | Low test coverage highlighted (absence of glow = uncovered) | File being edited by an agent right now |
| Transient effects | — | Debt delta when playing history (building grows red / shrinks green) | Agent avatars moving between buildings; edits, test runs and results; conflict alerts where two actors touch the same file |

Height and footprint stay constant across layers so the city shape remains recognizable. CI/CD effects (builds, deploys) belong to the agents layer when triggered by an agent, and to an optional CI layer otherwise.

**Debt metrics:** the hotspot score follows the "code as a crime scene" approach (Tornhill): complexity alone is not enough, since complex code that never changes is low priority. Churn is measured over a configurable window (e.g. last 6 months).

The complexity side of the score uses **decision points** (cyclomatic complexity minus the base 1 of each function), not summed complexity. Summed complexity rewards files with many trivial functions: on the first real repository analyzed, test files full of `it(...)` callbacks topped the ranking above the actual business logic. Test files are also marked with `role: "test"` in the model, so the debt layer can show or filter them separately.

### 2.3 Layout stability — **Decided as a requirement**
The commit time machine only works if buildings keep their positions as the code evolves. Squarified treemaps reshuffle the whole city when one file changes.

Requirements for the layout algorithm:
* Deterministic placement (same input → same city).
* Incremental: adding/removing a file only affects its block locally.
* Identity tracked across renames and moves (`git log --follow` / rename detection), so a moved file is animated, not demolished and rebuilt.
* Positions persisted in the city model, not recomputed per frame.

### 2.4 Branch multiverse representation — **Open**
One full island per branch duplicates the entire city; 30 feature branches become an unreadable archipelago.

**Recommendation:** render `develop`/`main` as the base city and each branch as a **diff overlay** (ghost/modified buildings), with full islands only for a few long-lived branches. Conflict prediction requires a `git merge-tree` per branch pair, so it must be cached and limited to branches selected by the user.

### 2.5 Privacy and team perception — **Open**
Real-time avatars showing who is editing what can be perceived as productivity surveillance, which is an adoption risk. Proposed stance:
* IDE presence is opt-in per developer.
* Default views show aggregated activity (a block is "active"), not named individuals.
* No historical per-person activity metrics.

---

## 3. Proposed Architecture

The system is split into independent layers around a **versioned city model**:

```
┌──────────────────────┐     ┌───────────────────────────┐     ┌─────────────────────┐
│ Analyzers            │     │ City model                │     │ Clients             │
│  - Static analysis   │ ──► │  (versioned schema,       │ ──► │  - 3D renderer      │
│  - Git history       │     │   snapshots + deltas)     │     │  - 2D/list fallback │
│  - Event ingestion   │     │                           │     │  - AI agents (MCP)  │
└──────────────────────┘     └───────────────────────────┘     └─────────────────────┘
```

### 3.1 Analyzers
* **Static analysis:** parsing with tree-sitter (multi-language); LOC via `scc`/`tokei`; complexity via `lizard` or tree-sitter queries; import graph per language; coverage from standard reports (LCOV, Cobertura, JaCoCo).
* **Git history:** libgit2 bindings for commits, branches, tags, renames and churn.
* **Event ingestion:** CI webhooks (GitHub Actions, GitLab CI, etc.), an optional IDE extension for presence, and agent activity. Agent activity sources, in order of priority:
  * agent hook systems (e.g. Claude Code hooks on tool calls such as file reads/edits and command runs), which give real-time, per-file events;
  * agent session transcripts/logs, for replaying past sessions;
  * git as a fallback (agent branches/worktrees, commit trailers such as `Co-Authored-By`), which works for any agent but only at commit granularity.

Analyzers run as a CLI first (testable without any 3D), later as a service.

### 3.2 City model
* A documented, versioned schema (e.g. JSON Schema) describing regions, districts, blocks, buildings, edges and metrics.
* **Snapshots** per commit (or sampled commits) plus **deltas** between them for playback.
* Layout positions stored in the model (see 2.3).
* The model is the contract between analyzers and clients; either side can be replaced independently.

### 3.3 Clients
* **3D renderer (web):** Three.js / React Three Fiber or Babylon.js. A game engine (Unity/Unreal/Godot) only pays off if VR or heavy multiplayer becomes a priority.
* **2D fallback:** treemap or list view for accessibility and day-to-day use.
* **AI agents:** expose the city model through an MCP server, so agents can query structure, hotspots and history. This makes the city a shared representation between humans and agents, not just a screen.

### 3.4 Scale
Monorepos with 100k+ files require from the start:
* GPU instancing for buildings;
* level of detail (a distant district renders as a single aggregated block);
* on-demand loading of districts and history.

### 3.5 Actionability
Every visual element must link back to the real artifact: clicking a building opens the file (editor or web), a CI effect opens the job log, an agent opens its session/PR.

---

## 4. Phased Plan

| Phase | Scope | Validates |
|---|---|---|
| **1. Debt city (MVP)** | One language; CLI generates the city model from static analysis + git churn + coverage report; web renderer with base and debt layers; ranked hotspot list next to the city; click-to-open file. | The metaphor is readable and the hotspots match what the team already suspects (and reveal some it does not). |
| **2. Live agents** | Event ingestion from agent hooks; agents layer with live avatars, per-file edit glow and test results; conflict alerts when two actors touch the same file; session view (what an agent changed). | Real-time pipeline and the AI-oversight use case. |
| **3. Agents ↔ debt** | MCP server over the city model (agents query hotspots and structure); per-session debt delta (did this agent session raise or lower the hotspot score?). | The combined differentiator (2.1). |
| **4. Time machine** | Snapshots/deltas over git history with stable layout and rename tracking; playback of debt evolution; agent session replay; tags as landmarks. | Layout stability and history performance. |
| **5. CI, multiverse and collaboration** | Non-agent CI/CD effects, branch diff overlays, conflict prediction, human IDE presence, war rooms, spatial audio, multiplayer. | Highest cost and least proven value for the chosen use cases; only after 1–4 succeed. |

### 4.1 Phase 1 technical decisions — **Decided**

* **Analyzed language:** TypeScript (`.ts`, `.tsx`, `.mts`, `.cts`; declaration files excluded).
* **Analyzer stack:** Python CLI (`analyzer/`), using tree-sitter for parsing (LOC, cyclomatic complexity and imports in one pass), the git CLI for churn (following renames) and LCOV for coverage.
* **City model:** `schema/city-model.schema.json` (v0.2.0) holds raw metrics and the layout; clients decide the visual mapping.
* **Renderer and other clients:** TypeScript, running in the browser, with **React Three Fiber** (Three.js) plus drei and postprocessing (`renderer/`). Clients consume the city model JSON only and never import analyzer code; the TypeScript model types are generated from the JSON Schema (`npm run gen:types`).
* **Visual direction:** futuristic / neon rather than plain boxes. All buildings share one shape so height and footprint stay comparable. The chosen shape is a **stack of hollow hexagonal rings with a light beam through the core** (one ring per "floor", so height can be counted; the gaps let towers behind stay visible in dense cities). The rings carry the layer colour (debt heat or module); the core beam carries energy pulses, and is the slot reserved for agent activity in phase 2. A solid prism variant remains available as a toggle. The style comes from instanced shaders (glowing edges, fresnel glass, pulse proportional to the hotspot score, holographic scan on the selected tower) plus bloom. Imports are arcs of light between rooftops.
* **Stack summary:** Python for analysis (`analyzer/`), TypeScript for clients, JSON Schema as the contract between them.

**Stable layout (implemented, see 2.3):** `codeland-analyze --previous <city.json>` keeps every child at its previous position inside its district. Removed files leave a vacant lot, new files are appended after the existing ones, and only growth pushes neighbours (a wider child pushes the later children of its row, a deeper row pushes the rows below). On bella-nina, adding one file and removing another moved 4 of 26 buildings by 2 units, against 20 of 26 by up to 10 units with a fresh layout. Vacant lots accumulate over time; a run without `--previous` re-plans the city compactly (a deliberate "re-zoning", not something to do on every run).

Current limitations of the analyzer: tsconfig `paths`/`baseUrl` aliases count as external imports; growth has no slack, so a building gaining one import still shifts its later neighbours by a small amount.

Stable layout (2.3) is a requirement from phase 1 even though playback only arrives in phase 4: positions must not change between analysis runs, otherwise the live agents view also jumps around.

### 4.2 Phase 2 technical decisions (live agents) — **Implemented, first version**

```
Claude Code session ──hooks (curl, 1 s timeout)──► codeland-live (aiohttp, 127.0.0.1:4317)
                                                     POST /events   raw hook payload in
                                                     GET  /ws       normalized events out ──► renderer
```

* **Capture:** Claude Code hooks (`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`, `SessionEnd`) installed by `codeland-live install-hooks <repo>` into `<repo>/.claude/settings.local.json` (personal, git-ignored). The hook is a `curl` that always exits 0, so a stopped server never slows or blocks the agent. Every Claude Code session is one agent (`session_id`).
* **Privacy:** the server keeps only routing information (agent, kind, phase, repo-relative path, tool, a short label). File contents, edit strings, tool responses and full commands are dropped on arrival and never reach clients; the server binds to localhost only. This also covers the surveillance concern of 2.5 for agents; human presence remains out of scope.
* **Contract:** `schema/agent-event.schema.json` (v0.3.0): a `snapshot` (recent history, sent on connect) followed by `agent-event` messages. Kinds: read, edit (Write/Edit/MultiEdit/NotebookEdit), search (Grep/Glob, targeting a folder), command (Bash), lifecycle (session-start, idle, session-end).
* **Test outcomes:** when a finished Bash command looks like a test run (vitest, jest, pytest, `npm test`, `go test`, ...), the event carries `tests: {outcome, passed, failed}`. The verdict comes from the `PostToolUseFailure` hook (non-zero exit) or from a parsed `N passed` / `N failed` summary; the output itself is never forwarded. The agents panel shows each agent's latest verdict. Not covered yet: attributing failures to files.
* **What changed per session:** `live/changes.py` measures an edited TypeScript file on disk (LOC and decisions) when the agent's first edit of it *starts* (baseline) and whenever an edit *ends*; the event carries `change: {before, after}` (null before = created, null after = deleted). The renderer keeps the first baseline and the latest result per agent and shows, per agent, files changed with the delta in lines and decisions (more decisions = more debt; fewer = debt paid down). Limits: edits done through Bash (`sed`, formatters) are not measured, the baseline is per agent (another agent's earlier edits are part of it), and only numbers leave the server.
* **Renderer — agents layer:** buildings dim to neutral; a file an agent read or edited lights up (rings and core beam) in the agent's colour and fades out (reads ~10 s, edits ~30 s). In every layer, agents are glowing orbs that fly to the file/folder they work on (hovering over the city centre for commands, parked around the city when idle), and the core beam of a touched file flares in the agent's colour. A **conflict** is a file edited by two or more live agents within 120 s: a spinning red ring over the tower and an alert in the agents panel.
* **Demo without agents:** `codeland-live simulate <repo> --city <city.json>` replays realistic fake hook payloads (two agents, ending in a conflict on the hottest file).

**Status after the pivot (section 0):** phase 2 stays as implemented and tested but is paused: it is not extended and is hidden by default in the new UI. It becomes useful again as the delivery channel for sweep agents.

---

## 6. Findings dashboard (pivot) — **Decided**

```
Scanners (Semgrep, CodeQL, ESLint, Trivy, ...)  ──SARIF──┐
Sweep agents (future: security, ...)            ──SARIF──┼─► codeland-analyze ──► city model (+ findings) ──► renderer
Native analysis (complexity, churn, coverage)   ─────────┘
```

### 6.1 Contract
Findings live **inside the city model** (schema v0.3.0, a new top-level `findings` array plus `analysis.findingSources`), so the renderer still loads one file and the layout stays shared. Each finding links to a building by repo-relative `path`. The renderer depends on the model only, never on SARIF.

| Field | Meaning |
|---|---|
| `id` | Stable fingerprint (see 6.3). |
| `ruleId`, `title` | Rule that fired, short human name. |
| `category` | `security`, `reliability`, `maintainability`, `testing`, `dependencies`, `performance`, `other` (open to extension). |
| `severity` | `critical`, `high`, `medium`, `low`, `info`. |
| `message` | Tool message, truncated. |
| `location` | `path` plus optional `startLine`/`endLine`. Results with no location, or located outside the repository, are dropped and counted per source in `analysis.findingSources`; findings in repository files that are not buildings (e.g. `package-lock.json`) are kept and shown in the panel only. |
| `source` | `{tool, version, kind}`; kind is `scanner`, `native` or `agent`. |
| `status` | `open` or `suppressed` (from SARIF suppressions); triage states come later (6.4). |

**Priority is computed in the renderer**, not stored: severity × how much the file matters (hotspot score and churn) × lack of coverage. Weights can then change without re-analysis, and the same finding ranks higher in a file that changes every week.

### 6.2 SARIF import
* `codeland-analyze <repo> --sarif a.sarif --sarif b.sarif` (repeatable). Only SARIF 2.1.0 is accepted; anything else fails with a clear message.
* **Severity:** the rule's `security-severity` property (CVSS 0–10, the convention GitHub Code Scanning uses) when present (≥9 critical, ≥7 high, ≥4 medium, else low); otherwise the result's `level` (`error` → high, `warning` → medium, `note` → low, `none` → info).
* **Category:** rule tags (`security`, `maintainability`, ...), then the rule id prefix of known tools, then `other`.
* **Paths:** `artifactLocation.uri` is resolved against `uriBaseId`/`originalUriBaseIds`, `file://` URIs and absolute paths are made repo-relative; results outside the repository are dropped and counted.
* Suppressed results (`suppressions`) are kept with `status: suppressed` and hidden by default.

### 6.3 Identity across scans
A finding needs the same `id` between scans or neither trends nor triage can work. Order of preference: the SARIF `partialFingerprints` / `fingerprints` when the tool provides them, else a hash of `(tool, ruleId, path, normalized snippet or message)`. **Line numbers are never part of the hash**, so a finding survives code moving up and down the file. Stable layout (2.3) gives the same property for the map.

### 6.4 Native findings
Codeland turns what it already measures into maintainability findings, with `source.kind = native` and rule ids under `codeland/`: very high decision count in one file, hotspot (complexity × churn), low coverage in a changing file, and later circular imports. Thresholds are CLI options (`--max-decisions`, `--min-coverage`, `--no-native`); the hotspot rule also needs at least 10 decision points, because the hotspot score is relative and the top file of a small repository is always 1.0. They are deliberately few: scanners are better at everything else.

### 6.5 UI
* **Layer "Problems":** tower colour follows the highest-priority open finding (category colour or severity ramp, switchable); count or beam intensity shows how many; the existing debt and structure layers stay.
* **Side panel (2D):** counts by category and severity, filters, and a list ordered by priority; clicking an item flies to the tower and opens the finding. Implemented in step B: the tower colour is the worst visible finding on the heat ramp (info cyan to critical magenta-red), clean towers go dim, filters are category chips, a minimum-severity chip, suppressed toggle and text search, the list shows the top 40 by priority, and clicking a finding flies to its tower and opens a detail card. Priority = severity weight (10/6/3/1.5/0.5) x (1 + 2 x hotspot + churn / max churn) x (1 + 0.5 x uncovered share), halved for test files; findings in files that are not buildings use the plain severity weight. The live agent connection is off unless the page is opened with `?live=1` (or `?live=<ws url>`), and the Agents layer only appears then. Triage (accept / ignore / resolved) is stored in a sidecar file keyed by finding `id`, designed in after the first working version.

### 6.6 Revised plan

| Step | Scope |
|---|---|
| **A. Findings in the model** — *implemented* | Schema v0.3.0, SARIF importer, native findings, tests with real SARIF samples. |
| **B. Problems layer and panel** — *implemented* | Renderer layer, filters, priority ordering, click-to-fly. |
| **C. Real scanners on bella-nina** — *implemented* | ESLint 9 (typescript-eslint, SARIF formatter) and Semgrep 1.18x (Docker; the pip build does not run on Windows) ran on bella-nina and on a copy with planted problems. bella-nina itself is clean for both (0 findings), so the planted copy is what exercised the importer. Real output exposed three things the hand-written fixtures hid: containers and CI report absolute paths outside the repo (`/src/src/a.ts`; now matched by their longest tail that is a repo file), Semgrep OSS writes the fingerprint `requires login` on every result (ignored: values with spaces), and linters report must-fix style rules as `error` (a maintainability finding from `level` alone is capped at medium). Semgrep only scans git-tracked files. |
| **D. Trend and triage** — *implemented* | Schema v0.4.0. Trend: `--previous` now also carries `firstSeen` per finding and `analysis.trend {since, fixed[]}`; a finding is *new* when `firstSeen > since`; a previous finding is *fixed* only if its tool reported again in this run (omitting a report is not a fix). Triage: see 6.7. |
| **E. Sweep agents** — *implemented* | The contract (6.8), cross-tool deduplication (6.9) and `codeland-sweep` (6.10). Delivery through the paused live channel is not built; it would sit on the same contract. |

### 6.7 Triage
Decisions live in a sidecar file, `codeland-triage.json` (`{version: 1, findings: {<id>: {state, note, at}}}`), kept next to the repository and committed with it, so the team shares them and they survive re-scans because ids are stable (6.3). States: `accepted` (known risk, left as is) and `false-positive`; "resolved" is not a state, it is what the trend reports when the finding disappears. `codeland-triage <file> accepted|false-positive|reopen <id>... [--note]` edits the file and `codeland-analyze --triage <file>` merges it into `finding.triage`; entries matching no finding are reported as stale and kept. The renderer is a static page that cannot write files, so the finding card shows the id and copies the command instead of editing. Triaged findings are hidden like scanner-suppressed ones (one toggle shows both) and no longer count as new.

### 6.8 Sweep agent contract
A sweep agent (security first, but any review: reliability, dependencies, tests...) is a program or a model session that reads the repository and writes a SARIF 2.1.0 file; `codeland-analyze --sarif sweep.sarif` imports it like any scanner. What makes it an *agent* report and keeps it comparable between runs:

| Field | Rule |
|---|---|
| `tool.driver.name` / `semanticVersion` | Name of the sweep (`claude-code-sweep-security`) and the model id (`claude-sonnet-5-5`). |
| `tool.driver.properties["codeland/kind"]` | `"agent"`. Sets `source.kind`, which the finding card shows as "agente". Absent = scanner. |
| `rules[].id` | `agent/<category>/<slug>`, with `<category>` one of the model's categories (`security`, `reliability`, `maintainability`, `testing`, `dependencies`, `performance`, `other`); it sets `category`. Tags are used first when present. |
| severity | `properties["security-severity"]` (CVSS 0-10) when the agent can justify a score, else `level` (`error` high, `warning` medium, `note` low). Maintainability findings from `level` alone are capped at medium. |
| `results[].fingerprints["codeland/finding/v1"]` | **The id the agent chooses**, short and about *what* and *where* (`command-injection:run`, `hardcoded-secret:apiToken`): the same problem must get the same string in every run, whatever words the explanation uses. Without it the id falls back to rule + path + `region.snippet.text` (so give a snippet), and only then to the message, which an LLM rewrites on every run. |
| `locations[0].physicalLocation` | Repository-relative `artifactLocation.uri` and `region.startLine`/`endLine`. A result without a location is dropped and counted. |
| `message.text` | One or two sentences: what is wrong and why it matters; truncated at 300 characters. |

Agent findings are opinions, not proofs, so they go through the same triage (6.7) as the rest. The same flaw reported by a scanner and by an agent is merged by 6.9. A sample report is `analyzer/tests/fixtures/sarif/agent.sarif`; the prompt below is enough to ask a Claude Code session for one:

> Review `<repo>` for `<security | reliability | ...>` problems. Write a SARIF 2.1.0 file to `<out>.sarif`: driver name `claude-code-sweep-<kind>`, `semanticVersion` your model id, `properties` `{"codeland/kind": "agent"}`; one result per problem with `ruleId` `agent/<category>/<slug>`, `level`, a one-to-two sentence `message`, a repo-relative `uri`, `startLine`, a `region.snippet.text` and `fingerprints` `{"codeland/finding/v1": "<slug>:<symbol>"}` that you would write identically on a re-run. Report only problems you can point at; no style nits.

### 6.9 Cross-tool deduplication
Scanners and agents often report the same flaw. Schema v0.5.0 adds `finding.duplicateOf`: the analyzer marks a finding as a repeat of another when **different tools** report them in the **same file and category** on **overlapping lines** (`dedupe.py`). Nothing is dropped and ids do not change, so trend and triage keep working; the more severe finding (then scanner before agent before native, then tool name and id) stays the primary. A finding is only marked against a primary, so a chain of overlaps cannot hide a finding nobody else reported, and one tool's own findings never merge with each other. Findings without lines (native, lock files) are never merged. Clients hide repeats, list them on the primary ("Também em" in the card, `+N` in the list) and raise the primary's priority by 25% per extra source (at most two), since two independent tools agreeing is the best confidence signal available. A triage decision on a repeat also applies to its primary, because which copy is primary can change between runs. Known limits: the match is deliberately strict (adjacent lines or a different category do not merge, so a Semgrep rule without a security tag will not merge with an agent's security finding), and a primary can hide a distinct same-line finding of another category of its own tool only through the "Também em" list, not as its own row.

### 6.10 `codeland-sweep`
`codeland-sweep <repo> --kind security|reliability|maintainability|testing|performance|dependencies [--path src/] [--chunk 40] [--runs 3] [--incremental] [--model] [--budget 2] [-o x.sarif] [--city city.json --sarif other.sarif --triage t.json]` runs one headless Claude Code session (`claude -p`) in the repository and saves the result as a SARIF file of the 6.8 contract; with `--city` it then re-analyzes the city, using an existing city file as the `--previous` model, so the trend shows what the sweep added.
* **Read-only by construction:** the session gets only `Read`, `Glob` and `Grep` (`--tools`), no session persistence and a spending cap (`--max-budget-usd`, default 2). It cannot edit the repository or run commands; the agent *answers* with the SARIF and Codeland writes the file, outside the repository.
* **The prompt is the contract** (`sweep.build_prompt`): kind-specific focus, the list of files in scope (git-tracked TypeScript, narrowed by `--path`), "only problems you can point at", the SARIF shape and the fingerprint rule.
* **Normalization enforces what the model may get wrong** (`sweep.normalize`): the answer may carry a code fence or a sentence around the JSON; the driver name, model id and `codeland/kind` are set by Codeland; rule ids are forced to `agent/<kind>/<slug>`; results outside the scope or without a rule are dropped and counted; at most 100 results; results without a `codeland/finding/v1` fingerprint are counted in a note (their ids then come from the snippet).
* **Measured, small file** (bella-nina copy, `legacy.ts`, security, Sonnet 5.5): about 20 seconds per run; two runs found the same 4 problems with identical fingerprints.
* **Measured, 21 files / about 3,000 lines** (Codeland's own `renderer/src`, security): 5 turns, 13 to 16 seconds and US$0.03 to 0.09 per run. The findings were real: the WebSocket URL and the model URL both come from query parameters and are used unvalidated; a reliability run also found a real stale-async race in `App.tsx`. Stability was the weak point, and what the measurement changed:
  * With free-form rule slugs, one run in five found nothing and the problem was named `untrusted-websocket-url` in some runs and `untrusted-url-parameter` in others, so its id changed. Fix: a closed vocabulary of slugs per kind (`sweep.SLUGS`, given to the agent in the prompt and enforced in `normalize`; anything else becomes `other`), and the symbol of the fingerprint reduced to its last dotted segment.
  * After that, over 5 runs: `untrusted-input:liveUrl` in 5 of 5 and `loadDefaultModel` in 4 of 5 (the fifth called it `ssrf`). The agent still varies in *which* symbol it hangs a related finding on (`onmessage`, `parseModel`, `useLive`), so one or two secondary findings per run may show up as new/fixed in the trend.
  * `--runs N` runs the agent N times and keeps the union by fingerprint: a run that misses something is covered by the next. With `--runs 3` the union had the 4 findings seen across the single runs for about US$0.15. Use it when the trend matters.
  * Not measured: recall against known vulnerabilities (the findings were judged by reading the code, not against a benchmark).
* **Measured, 160 files** (a TypeScript monorepo, API plus web portal, security, Sonnet 5.5). Findings were specific and the ones checked against the code were correct (a rate-limit bucket built from 20 characters of a key whose lookup prefix has 16, an SSRF blocklist that never matches bracketed IPv6 hostnames, a delete that is scoped by tenant but not by workspace). Stability at this size was poor, which is the main result:
  * One session over all 160 files took 25 to 33 turns, 60 to 85 seconds and US$0.34 to 0.57, and found 5 to 8 problems; across three runs only **1 problem of 14** was found every time. The agent reads a different subset each run.
  * Splitting the scope fixes most of it. With chunks of 25 to 50 files, two runs per chunk agreed on 3 of 8, 3 of 7 and 3 of 4 findings (the smallest chunk was the most stable), and the union of the chunked runs had 22 distinct findings against 14 for three whole-scope runs. Seven chunked sessions cost about US$2.3.
  * `--chunk N` does this automatically (sorted files in slices of N, so folders stay together; sessions are merged by fingerprint and a failed session is reported without losing the rest): `--chunk 40` over the same repository ran 4 sessions in 3.5 minutes for US$1.03 and produced 14 findings. Rule of thumb from these numbers: chunks of 25 to 40 files, and `--runs 2` or `3` when the trend matters; expect secondary findings to differ from run to run.
  * One session failed silently during the measurement (no report, no message visible because of how it was run); sessions are now tolerant and the failure is a note on the report.
  * A real bug surfaced only at this scale: one result carried `message` as a bare string instead of `{ "text": ... }` and crashed the importer. `normalize` now corrects it and the importer tolerates it.
  * Still not measured: repositories of many hundreds of files, and cost growth beyond about 160 files (roughly linear in the files read, so budget with `--budget` per session).
* **Incremental sweep** (`--incremental`): the SARIF file doubles as the sweep's memory. Its run carries `properties["codeland/sweep"] = {kind, version, files: {path: git blob hash}}`, the content hash of every file already reviewed. If `-o` already exists with the same kind and prompt version, only the files whose hash differs (committed or not) are sent to the agent; findings of untouched files are carried over, findings of reviewed files are replaced (so a fixed problem disappears), files that no longer exist are forgotten, and a file in a session that failed has no hash and is retried next time. `--path` keeps what the earlier report knew about files outside it. `STATE_VERSION` must be bumped when the prompt or the slug vocabulary changes, so old state is not trusted. Measured on the planted-problems copy (31 files): the first run reviews everything; fixing the weak hash in one file and running again reviewed **1 of 31 files** (2 turns, US$0.03, 10 seconds), dropped that finding and kept the other 5. Unchanged runs do not call the agent at all. Limit: a change in one file can create or remove a finding in another (a caller of a function that became unsafe), which an incremental run does not see; sweep fully now and then.
* **Retries:** a session whose answer is not valid SARIF is tried once more (an intermittent failure seen at 160 files and again on the small copy); a missing `claude` CLI aborts at once.
* **Not done:** one kind per run.

---

## 5. Key Risks

| Risk | Mitigation |
|---|---|
| Impressive in demos, unused day-to-day | Anchor on one use case and its questions (2.1); keep the 2D fallback and click-through. |
| Visual overload | Encoding table and layers (2.2). |
| Unreadable history playback | Stable, incremental layout (2.3). |
| Poor performance on large repos | Instancing, LOD, on-demand loading (3.4). |
| Team rejection due to surveillance perception | Opt-in, aggregated presence (2.5). |
| Multi-language analysis cost | Start with one language; tree-sitter for extension. |
