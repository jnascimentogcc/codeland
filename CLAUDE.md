# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The repository is at the pre-implementation stage: it contains only `LICENSE` and design documents in `docs/`. There is no source code, build system, package manifest, linter, or test suite yet, so there are no build/lint/test commands to document. Update this file once a stack is chosen and code lands.

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
