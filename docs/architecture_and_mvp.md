# Codeland – Architecture Considerations and MVP Plan

This document builds on the initial vision in [codeland_concept.md](codeland_concept.md). It records the open decisions, the proposed architecture and a phased plan for a first usable version. It is a working document: decisions marked **Open** still need an owner and an answer.

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

Stable layout (2.3) is a requirement from phase 1 even though playback only arrives in phase 4: positions must not change between analysis runs, otherwise the live agents view also jumps around.

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
