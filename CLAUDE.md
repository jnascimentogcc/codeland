# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout and commands

- `tree-sitter` is pinned `<0.26`: 0.26.0 crashes natively (access violation) on Windows when walking larger trees; `test_large_source_does_not_crash` guards it.
- `schema/city-model.schema.json` – the city model contract (JSON Schema) between analyzers and clients. Changing the model means bumping `schemaVersion` here and `SCHEMA_VERSION` in `analyzer/src/codeland_analyzer/__init__.py`.
- `analyzer/` – Python CLI (uv project) that builds the city model from a TypeScript git repository. No renderer exists yet.

Run from `analyzer/`:

```bash
uv sync                                        # install deps (incl. dev group)
uv run pytest                                  # all tests
uv run pytest tests/test_parse.py::test_metrics_of_typescript_source   # single test
uv run ruff check . && uv run ruff format .    # lint + format
uv run codeland-analyze <repo> -o city.json [--churn-days 180] [--coverage lcov.info] [--include-tests]
```

## Analyzer architecture

`build.analyze()` orchestrates independent modules and assembles the model dict:

- `gitrepo` – git CLI wrapper; source files come from `git ls-files --cached --others --exclude-standard` (so ignored dirs like `node_modules` are skipped; `.d.ts` excluded).
- `parse` – one tree-sitter pass per file yields LOC (lines with non-comment tokens), cyclomatic complexity (per function, nested functions counted separately, plus top-level decisions) and import references (import / re-export / dynamic import / require).
- `resolve` – resolves only relative specifiers to repo files (incl. `./x.js` → `x.ts`, `index.ts`); bare specifiers are external.
- `churn` – `git log -M --numstat` newest-first, folding history of renamed files into the current path.
- `coverage` – LCOV parser, paths normalized to repo-relative.
- `layout` – deterministic nested shelf-packing (folders → districts, files → buildings; footprint from import count), choosing per district the row width that gives the most square shape. Layout positions live in the model because stability across runs is a design requirement.

The hotspot score is normalized **decisions** (complexity minus one per function) × normalized churn commits; summed complexity is deliberately not used because it ranks test files with many trivial callbacks above real logic. Files are tagged `role: source|test` (`gitrepo.is_test`), and the CLI hotspot list skips tests unless `--include-tests`. Tests build real temporary git repos via the `repo` fixture in `tests/conftest.py`, and `test_build.py` validates output against the schema.

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
- The analyzed language is TypeScript; the analyzer is Python (decided in `docs/architecture_and_mvp.md` §4.1).
