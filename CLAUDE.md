# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout and commands

- `tree-sitter` is pinned `<0.26`: 0.26.0 crashes natively (access violation) on Windows when walking larger trees; `test_large_source_does_not_crash` guards it.
- `schema/city-model.schema.json` – the city model contract (JSON Schema) between analyzers and clients. Changing the model means bumping `schemaVersion` here (currently 0.5.0; 0.3.0 added `findings`, 0.4.0 `firstSeen`, `triage` and `analysis.trend`, 0.5.0 `duplicateOf`), `SCHEMA_VERSION` in `analyzer/src/codeland_analyzer/__init__.py` and `SUPPORTED_SCHEMA_VERSION` in `renderer/src/model/load.ts`, then running `npm run gen:types` in `renderer/`.
- `schema/agent-event.schema.json` – the live contract: messages `codeland-live` sends over its WebSocket (snapshot + agent events). Generated into `renderer/src/model/agent-event.ts` by the same `npm run gen:types`.
- `analyzer/` – Python CLI (uv project) that builds the city model from a TypeScript git repository. It also hosts `codeland-live` (`src/codeland_analyzer/live/`), the live agent server.
- `renderer/` – React Three Fiber web app (Vite) that renders a city model. `three` is pinned `~0.186` because `postprocessing` 6.39 does not accept 0.187 yet.

Run from `analyzer/`:

```bash
uv sync                                        # install deps (incl. dev group)
uv run pytest                                  # all tests
uv run pytest tests/test_parse.py::test_metrics_of_typescript_source   # single test
uv run ruff check . && uv run ruff format .    # lint + format
uv run codeland-analyze <repo> -o city.json [--churn-days 180] [--coverage lcov.info] [--include-tests]
# LCOV for a vitest repo, without touching its package.json: npm i --no-save @vitest/coverage-v8, then
#   npx vitest run --coverage.enabled --coverage.reporter=lcovonly --coverage.reportsDirectory=<dir outside the repo>
# Files the tests never load are absent from the LCOV, so their coverage stays unknown (not dimmed), not 0.
uv run codeland-analyze <repo> -o ../renderer/public/city.json   # model the renderer loads by default
uv run codeland-analyze <repo> -o city.json --previous city.json  # re-analyze keeping the layout stable
uv run codeland-analyze <repo> -o city.json --sarif semgrep.sarif --sarif codeql.sarif   # import findings (SARIF 2.1.0 only); --no-native skips Codeland's own
uv run codeland-analyze <repo> -o city.json --previous city.json --triage codeland-triage.json   # trend (new/fixed) + human decisions
uv run codeland-triage codeland-triage.json accepted|false-positive|reopen <finding id>... --note "why"
uv run codeland-live serve <repo>              # live agent server on 127.0.0.1:4317 (POST /events, WS /ws)
uv run codeland-live install-hooks <repo>      # forward Claude Code hooks of <repo> (settings.local.json); uninstall-hooks removes them
uv run codeland-live simulate <repo> --city ../renderer/public/city.json   # fake agents for demos
```

`.claude/launch.json` has `renderer` and `live` configurations (the latter serves `../PoC/bella-nina`, the test repository used during development).

Run from `renderer/`:

```bash
npm install
npm run dev          # http://localhost:5173 (loads public/city.json, or ?model=<url>; a city.json can also be dropped on the page)
npm run typecheck
npm test             # vitest; single test: npx vitest run -t "centers the city"
npm run build
npm run gen:types    # regenerate src/model/city-model.ts and agent-event.ts from the schemas (do not edit them by hand)
```

`city.json` files are git-ignored: they are generated from other repositories.

## Analyzer architecture

`build.analyze()` orchestrates independent modules and assembles the model dict:

- `gitrepo` – git CLI wrapper; source files come from `git ls-files --cached --others --exclude-standard` (so ignored dirs like `node_modules` are skipped; `.d.ts` excluded).
- `parse` – one tree-sitter pass per file yields LOC (lines with non-comment tokens), cyclomatic complexity (per function, nested functions counted separately, plus top-level decisions) and import references (import / re-export / dynamic import / require).
- `resolve` – resolves only relative specifiers to repo files (incl. `./x.js` → `x.ts`, `index.ts`); bare specifiers are external.
- `churn` – `git log -M --numstat` newest-first, folding history of renamed files into the current path.
- `coverage` – LCOV parser, paths normalized to repo-relative.
- `sarif` – SARIF 2.1.0 importer: severity from `security-severity` (CVSS) else `level`, category from tags then tool/rule prefixes, paths made repo-relative (absolute paths outside the repo are matched by their longest tail that is a repo file, e.g. Semgrep in Docker; otherwise dropped and counted; placeholder fingerprints with spaces are ignored; level alone caps maintainability at medium), `tool.driver.properties["codeland/kind"] = "agent"` marks a sweep-agent report (`source.kind = agent`; contract in docs 6.8: rule ids `agent/<category>/<slug>`, own id in `fingerprints["codeland/finding/v1"]`), ids from the tool's fingerprints or a hash of rule + path + snippet/message, never line numbers (`tests/fixtures/sarif/` hold hand-written Semgrep, CodeQL and ESLint style reports). `dedupe` (`duplicateOf`: other tools' findings in the same file, category and overlapping lines; clients hide repeats and show them on the primary; docs 6.9), `trend` (firstSeen + fixed vs `--previous`) and `triage` (sidecar file keyed by finding id, edited by `codeland-triage`). `native` – Codeland's own findings (`codeland/high-complexity`, `codeland/hotspot`, `codeland/low-coverage`) from the metrics, ids from rule + path only. `build.collect_findings` merges both, sorted by path and line.
- `layout` – nested shelf-packing (folders → districts, files → buildings; footprint from import count). Two modes per district: *fresh* (children sorted by name, row width chosen for the most square shape) and *stable* (`--previous`: `slots_from_model` reads each child's position relative to its district back from the earlier model; `_place_stable` keeps those positions, leaves vacant lots for removed children, appends new ones, and lets growth push only later neighbours). Vacancies are preserved across runs because positions, not order, are read back. Don't "fix" the gaps by compacting in stable mode: stability across runs is a design requirement (time machine, live agents).

The hotspot score is normalized **decisions** (complexity minus one per function) × normalized churn commits; summed complexity is deliberately not used because it ranks test files with many trivial callbacks above real logic. Files are tagged `role: source|test` (`gitrepo.is_test`), and the CLI hotspot list skips tests unless `--include-tests`. Tests build real temporary git repos via the `repo` fixture in `tests/conftest.py`, and `test_build.py` validates output against the schema.

## Renderer architecture

- `src/model/view.ts` – pure mapping from the model to world space (city centered on the origin, height linear in LOC normalized over *all* buildings so hiding tests does not rescale, district plates stacked by depth, module hues). Unit-tested; keep three.js out of it.
- `src/scene/` – `Buildings` draws every tower as one `InstancedMesh` with the custom shader in `buildingMaterial.ts` (per-instance attributes `aHeat`, `aCoverage`, `aTest`, `aHue`; uniforms for layer, time, hovered/selected instance, `uRings`). The default "rings" shape is the same prism with the gap of every floor discarded in the fragment shader (floors counted from the roof down; `DoubleSide` so inner faces show, dimmed), plus a second `InstancedMesh` of additive core beams (`beamMaterial.ts`, raycast disabled) sharing instance indices with the towers. The beam is reserved for agent activity in phase 2. The look must come from that shader and bloom, never from per-building meshes, so large repos stay one draw call. Colors above 1.0 are deliberate (they drive the bloom). Instances are scaled non-uniformly, so normals use the inverse scale in the vertex shader.
- `Districts` (instanced plates + one line-segments outline), `ImportArcs` (bezier arcs; all faint, or only the selection's with flowing dashes), `CityCanvas` (scene, post-processing, camera rig with idle orbit and fly-to-selection).
- `src/model/findings.ts` – pure findings logic (priority, filters, facets, per-building worst severity; unit-tested). The "problems" layer (uniform 3) feeds the per-instance attribute `aProblem` (heat-ramp position of the worst visible finding, 0 = none) to both tower and beam shaders; the live agent connection is paused and only starts with `?live=1`.
- `src/ui/Hud.tsx` – DOM overlay (layer switch, shape switch, tests toggle, agents panel, hotspot ranking, details); UI text is in Portuguese.

## Live agents

- Server (`analyzer/src/codeland_analyzer/live/`): `normalize.py` turns a raw Claude Code hook payload into an agent event and is the privacy boundary (only agent, kind, phase, repo-relative path, tool and an 80-char label survive; never forward contents, diffs, tool responses or full commands; the only thing read from a response is the pass/fail verdict and counts of a test command, sent as `tests`; the `PostToolUseFailure` hook is what marks a non-zero exit). `server.py` keeps a bounded history, sends it as a snapshot on connect, then broadcasts. `changes.py` (`ChangeTracker`, owned by `LiveHub`) re-parses edited TypeScript files to attach `change: {before, after}` (LOC, decisions) to edit events; the baseline is taken at the first edit's PreToolUse, so hooks must stay synchronous. `hooks.py` installs a `curl ... || true # codeland-live` hook; the marker comment makes install idempotent and uninstall surgical.
- Renderer: `src/live/useLive.ts` (WebSocket with reconnect; `?live=<url>` or `?live=off`), `src/model/agents.ts` (pure reducer + conflict detection, unit-tested), `src/scene/Agents.tsx` (orbs, conflict rings). Per-building activity goes into the instanced attributes `aAgentHue`/`aActivityAt`/`aActivityKind` shared by tower and beam geometries; fading happens in the shaders against `uNow`. Activity timestamps are stored relative to `LIVE_EPOCH` because float32 cannot hold Unix seconds precisely.
- Layer uniform: 0 structure, 1 debt, 2 agents. In the agents layer towers go neutral and only activity colours them; in other layers activity shows only on the core beam and the orbs.

## Direction

The project pivoted from live agent oversight to a **code problems (findings) dashboard**: findings are imported from scanners as SARIF 2.1.0 (plus native maintainability findings), stored in the city model, and shown as a layer on the city plus a 2D panel. The live agent code (`analyzer/.../live/`, renderer `live/`, `Agents.tsx`) is kept but paused. Decisions and the step plan are in `docs/architecture_and_mvp.md` §0 and §6, which win over the older sections.

## Project concept

Codeland turns a source code repository (static structure, git history, CI/runtime metrics) into an interactive 3D virtual "city" where humans and AI agents collaborate visually. Two design documents, read both before designing anything:

- `docs/codeland_concept.md` – the initial vision only; treat it as inspiration, not as a spec.
- `docs/architecture_and_mvp.md` – the working decisions: primary use cases (**technical debt prioritization** and **AI agent oversight**), the visual encoding table (one metric per channel, switchable layers), stable-layout requirement, layered architecture (analyzers → versioned city model → clients, including an MCP server), and the phased plan. When it conflicts with the concept doc, it wins.

The concept doc is organized in three "fronts":

1. **Code Metropolis (static structure):** the urban metaphor. Repo/monorepo → metropolitan region; microservice/module → district; folder/package → city block; file/class → building; imports/dependencies → streets/bridges (light beams = data traffic). Building parameters: height ∝ LOC or cyclomatic complexity, footprint ∝ coupling (number of imports), material = code health (metal/glass for clean code, concrete/rust for legacy/debt), lighting = test status (blue/white glow for good coverage, red/yellow flashing for failures).
2. **Timeline and Branch Multiverse (git history):** each relevant branch is a parallel floating island; bridges between branches show merge-conflict alerts; a "commit time machine" allows playback of history (buildings growing/demolished); tags are crystal-portal monuments; hotfixes are shown as repair drones.
3. **Team Dynamics / Multiplayer (real-time events):** developer avatars and IDE presence (scaffolding/welding on files being edited), CI/CD as urban events (builds as delivery drones, tests as energy shields, deploys as fireworks), autonomous AI agents (audit drones, refactoring robots), and "war room" spaces with spatial audio.

Architecturally this implies three data layers feeding a 3D renderer: static code analysis (LOC, complexity, imports, coverage), git history (branches, commits, tags), and a real-time event stream (IDE presence, CI/CD, agents). Keep the metaphor mappings above consistent when adding features.

## Conventions

- Default/main branch is `develop`.
- The concept document is written in English; keep new docs in English unless told otherwise.
- Stack (decided in `docs/architecture_and_mvp.md` §4.1): the analyzer is Python; the renderer and other clients are TypeScript in the browser with React Three Fiber. The analyzed language is TypeScript. Clients depend only on the city model JSON, never on analyzer code.
