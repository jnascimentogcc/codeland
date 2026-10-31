"""codeland-sweep: runs a read-only Claude Code session over a repository and turns its answer into
a SARIF report that follows the sweep agent contract (docs 6.8, 6.10)."""

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeland_analyzer.gitrepo import file_hashes, list_source_files
from codeland_analyzer.sarif import FINGERPRINT_KEY, KIND_PROPERTY

KINDS = {
    "security": "security problems: injection, hard-coded secrets, unsafe deserialization or eval, "
    "weak cryptography, missing authentication or authorization, path traversal, SSRF",
    "reliability": "reliability bugs: unhandled promise rejections, missing await, race "
    "conditions, unchecked null or undefined, swallowed errors, resource leaks, wrong equality",
    "maintainability": "maintainability problems that cost real time: dead code, duplicated logic, "
    "functions doing several jobs, misleading names, hidden coupling",
    "testing": "testing gaps: important branches or error paths no test exercises, tests that "
    "assert nothing, tests coupled to implementation details",
    "performance": "performance problems: work repeated in loops, N+1 queries, blocking calls on "
    "hot paths, unbounded growth",
    "dependencies": "dependency problems visible in the code: deprecated or risky packages, "
    "unpinned versions, unused or duplicated dependencies",
}
# Closed vocabulary of rule slugs: an agent that is free to name a problem names it differently
# on every run (untrusted-websocket-url / untrusted-url-parameter), which changes the finding id.
SLUGS = {
    "security": (
        "command-injection code-injection sql-injection xss hardcoded-secret weak-crypto "
        "path-traversal ssrf unsafe-deserialization untrusted-input missing-auth other"
    ).split(),
    "reliability": (
        "unhandled-rejection missing-await race-condition stale-state null-dereference "
        "swallowed-error resource-leak wrong-comparison other"
    ).split(),
    "maintainability": (
        "dead-code duplication god-function misleading-name hidden-coupling other"
    ).split(),
    "testing": "untested-path empty-assertion brittle-test other".split(),
    "performance": "repeated-work n-plus-one blocking-call unbounded-growth other".split(),
    "dependencies": "risky-package unpinned-version unused-package duplicate-package other".split(),
}
SLUG_HELP = {
    "untrusted-input": "external data (URL parameters, messages, files) used without validation",
    "stale-state": "an async result that overwrites newer state or outlives its component",
}
MAX_RESULTS = 100
DEFAULT_MODEL = "claude-sonnet-5-5"
# Run property that makes a report resumable: the content hash of every file already swept.
STATE_KEY = "codeland/sweep"
STATE_VERSION = 1  # bump when the prompt or the vocabulary changes: old state no longer applies


class SweepError(Exception):
    pass


class AgentUnavailable(SweepError):
    """Retrying cannot help (no `claude` on PATH)."""


# (prompt, repo, model, budget in USD) -> the agent's final answer
Agent = Callable[[str, Path, str, float], str]


@dataclass
class SweepReport:
    document: dict[str, Any]
    results: int
    dropped: int = 0
    notes: list[str] = field(default_factory=list)
    swept: int = 0  # files sent to the agent in this run
    total: int = 0  # files in scope


def build_prompt(kind: str, files: list[str]) -> str:
    listing = "\n".join(f"- {path}" for path in files)
    return f"""You are a code review sweep agent. Review the TypeScript files below for
{KINDS[kind]}.

Files in scope (repository-relative paths):
{listing}

You can only read files. Read the code that matters; do not guess about files you did not open.
Report only problems you can point at in the code, with a real line number. No style nits.
At most {MAX_RESULTS} results; fewer is fine, and an empty list is a valid answer.

Your FINAL message must be a single SARIF 2.1.0 JSON document and nothing else (no prose, no
code fence), with exactly one run:
- tool.driver.name "claude-code-sweep-{kind}"; tool.driver.rules: one entry per ruleId with a
  shortDescription.text.
- One result per problem:
  - ruleId "agent/{kind}/<slug>" where <slug> is exactly one of: {", ".join(SLUGS[kind])}
    ({_slug_help(kind)}); use "other" only when none fits;
  - level "error" (exploitable or certain bug), "warning" or "note";
  - message.text: one or two sentences, what is wrong and why it matters;
  - locations[0].physicalLocation: artifactLocation.uri (repository-relative path from the list
    above) and region with startLine, endLine and snippet.text (the offending code, short);
  - fingerprints: {{"{FINGERPRINT_KEY}": "<slug>:<symbol>"}} where <symbol> is the one function
    or variable name the problem hangs on (no dots, no spaces). It must be what you would write
    again on a re-run, so base it on what and where, never on your wording."""


def _slug_help(kind: str) -> str:
    notes = [f"{slug}: {SLUG_HELP[slug]}" for slug in SLUGS[kind] if slug in SLUG_HELP]
    return "; ".join(notes) or "pick the closest one"


def run_claude(prompt: str, repo: Path, model: str, budget: float) -> str:
    """One headless Claude Code session restricted to read-only tools."""
    executable = shutil.which("claude")
    if executable is None:
        raise AgentUnavailable("the `claude` CLI (Claude Code) was not found on PATH")
    command = [
        executable,
        "-p",
        "--output-format",
        "json",
        "--tools",
        "Read,Glob,Grep",
        "--no-session-persistence",
        "--model",
        model,
        "--max-budget-usd",
        str(budget),
    ]
    done = subprocess.run(
        command,
        input=prompt,
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    try:
        reply = json.loads(done.stdout)
    except ValueError as error:
        detail = done.stderr.strip()[:300]
        raise SweepError(f"claude failed (exit {done.returncode}): {detail}") from error
    if reply.get("is_error") or not isinstance(reply.get("result"), str):
        raise SweepError(f"claude reported an error: {str(reply.get('result'))[:300]}")
    print(
        f"  claude: {reply.get('num_turns')} turns, ${reply.get('total_cost_usd')}, "
        f"{(reply.get('duration_ms') or 0) / 1000:.0f}s",
        file=sys.stderr,
    )
    return reply["result"]


def sweep(
    repo: Path,
    kind: str,
    *,
    agent: Agent | None = None,
    model: str = DEFAULT_MODEL,
    budget: float = 2.0,
    paths: list[str] | None = None,
    runs: int = 1,
    chunk: int | None = None,
    previous: dict[str, Any] | None = None,
) -> SweepReport:
    """Runs the agent and returns a normalized SARIF document (see `normalize`).

    chunk: review at most this many files per session (sorted, so folders stay together) and merge
    the results; one session over a large scope reads a different subset each time (docs 6.10).
    runs: sessions per chunk, merged by finding identity.
    previous: an earlier report of the same kind (incremental sweep): only files whose content
    changed since it are sent to the agent; the findings of untouched files are carried over and
    those of changed files are replaced. A file in a session that failed is retried next time.
    """
    if kind not in KINDS:
        raise SweepError(f"unknown kind {kind!r}; choose one of {', '.join(KINDS)}")
    repo = repo.resolve()
    everything = list_source_files(repo)
    scope = sorted(p for p in everything if not paths or any(p.startswith(x) for x in paths))
    if not scope:
        raise SweepError("no TypeScript files in scope")
    hashes = file_hashes(repo, everything)

    carried, state, rules = _resume(previous, kind, set(everything), set(scope), hashes)
    todo = [p for p in scope if state.get(p) != hashes[p]]
    groups = [todo[i : i + chunk] for i in range(0, len(todo), chunk)] if chunk else [todo]
    reports: list[SweepReport] = []
    failures: list[str] = []
    for group in filter(None, groups):
        prompt = build_prompt(kind, group)
        succeeded = False
        for _ in range(max(runs, 1)):
            try:
                reports.append(
                    _session(agent or run_claude, prompt, repo, model, budget, group, kind)
                )
                succeeded = True
            except AgentUnavailable:
                raise
            except SweepError as error:  # one failed session must not cost the others
                failures.append(str(error))
        for path in group if succeeded else []:
            state[path] = hashes[path]
    if todo and not reports:
        raise SweepError(failures[0])

    results: dict[str, dict[str, Any]] = {}
    for result in carried:
        results.setdefault(_key(result), result)
    for report in reports:
        run = report.document["runs"][0]
        rules.update({r["id"]: r for r in run["tool"]["driver"]["rules"]})
        for result in run["results"]:
            results.setdefault(_key(result), result)
    notes = sorted({n for report in reports for n in report.notes})
    if failures:
        sessions = len(failures) + len(reports)
        notes.append(f"{len(failures)} of {sessions} sessions failed: {failures[0]}")
    document = _document(kind, model, list(results.values()), rules, state)
    return SweepReport(
        document,
        len(results),
        sum(r.dropped for r in reports),
        notes,
        swept=len(todo),
        total=len(scope),
    )


def _session(
    agent: Agent, prompt: str, repo: Path, model: str, budget: float, group: list[str], kind: str
) -> SweepReport:
    """One session, tried twice: a model now and then answers with something that is not SARIF."""
    for attempt in (1, 2):
        try:
            return normalize(agent(prompt, repo, model, budget), kind, model, set(group))
        except AgentUnavailable:
            raise
        except SweepError:
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _key(result: dict[str, Any]) -> str:
    return f"{_result_path(result)}\x1f{result['fingerprints'][FINGERPRINT_KEY]}"


def _resume(
    previous: dict[str, Any] | None,
    kind: str,
    existing: set[str],
    scope: set[str],
    hashes: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    """(results to carry over, hash of each already swept file, their rule descriptions).

    A previous report only counts when it is a sweep of the same kind and prompt version; a file
    that no longer exists is forgotten and a file in scope whose content changed is swept again.
    Files outside the scope (`--path`) keep what the earlier report knew about them.
    """
    try:
        run = previous["runs"][0]  # type: ignore[index]
        meta = run["properties"][STATE_KEY]
        known = {p: h for p, h in meta["files"].items() if isinstance(h, str)}
        valid = meta["kind"] == kind and meta["version"] == STATE_VERSION
    except (KeyError, IndexError, TypeError, AttributeError):
        return [], {}, {}
    if not valid:
        return [], {}, {}
    state = {p: h for p, h in known.items() if p in existing and (p not in scope or h == hashes[p])}
    carried = [
        r
        for r in run.get("results") or []
        if _result_path(r) in state and (r.get("fingerprints") or {}).get(FINGERPRINT_KEY)
    ]
    rules = {r["id"]: r for r in run["tool"]["driver"].get("rules") or [] if "id" in r}
    return carried, state, rules


def _document(
    kind: str,
    model: str,
    results: list[dict[str, Any]],
    rules: dict[str, dict[str, Any]],
    state: dict[str, str],
) -> dict[str, Any]:
    results.sort(key=lambda r: (_result_path(r) or "", r["fingerprints"][FINGERPRINT_KEY]))
    used = sorted({r["ruleId"] for r in results})
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": f"claude-code-sweep-{kind}",
                        "semanticVersion": model,
                        "properties": {KIND_PROPERTY: "agent"},
                        "rules": [{**rules.get(rule_id, {}), "id": rule_id} for rule_id in used],
                    }
                },
                "properties": {
                    STATE_KEY: {
                        "kind": kind,
                        "version": STATE_VERSION,
                        "files": dict(sorted(state.items())),
                    }
                },
                "results": results,
            }
        ],
    }


def normalize(answer: str, kind: str, model: str, files: set[str]) -> SweepReport:
    """Parses the agent's answer and enforces the contract: marks it as an agent report, keeps
    `agent/<kind>/` rule ids, drops results outside the scope, caps the number of results."""
    document = _extract_json(answer)
    runs = document.get("runs") if isinstance(document, dict) else None
    if not isinstance(runs, list) or not runs or not isinstance(runs[0], dict):
        raise SweepError("the agent's answer is not a SARIF document with a run")
    run = runs[0]
    kept: list[dict[str, Any]] = []
    dropped = unnamed = 0
    for result in run.get("results") or []:
        if _result_path(result) not in files or not isinstance(result.get("ruleId"), str):
            dropped += 1
            continue
        result["ruleId"] = _rule_id(kind, result["ruleId"])
        if isinstance(result.get("message"), str):  # models sometimes write the bare string
            result["message"] = {"text": result["message"]}
        fingerprint, named = _fingerprint(result)
        unnamed += not named
        result["fingerprints"] = {
            **(result.get("fingerprints") or {}),
            FINGERPRINT_KEY: fingerprint,
        }
        kept.append(result)
    if len(kept) > MAX_RESULTS:
        dropped += len(kept) - MAX_RESULTS
        kept = kept[:MAX_RESULTS]
    notes = (
        [f"{unnamed} results name no symbol in {FINGERPRINT_KEY}: their ids use the line number"]
        if unnamed
        else []
    )
    unique: dict[str, dict[str, Any]] = {}
    for result in kept:
        unique.setdefault(_key(result), result)
    dropped += len(kept) - len(unique)  # the same slug and symbol twice is one finding
    kept = list(unique.values())

    driver = run.get("tool", {}).get("driver", {}) if isinstance(run.get("tool"), dict) else {}
    described = {
        _rule_id(kind, rule["id"]): rule
        for rule in driver.get("rules") or []
        if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }
    rules = {
        rule_id: {**described.get(rule_id, {}), "id": rule_id}
        for rule_id in sorted({r["ruleId"] for r in kept})
    }
    return SweepReport(_document(kind, model, kept, rules, {}), len(kept), dropped, notes)


def _rule_id(kind: str, raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower().split("/")[-1]).strip("-")
    return f"agent/{kind}/{slug if slug in SLUGS[kind] else 'other'}"


def _fingerprint(result: dict[str, Any]) -> tuple[str, bool]:
    """`<slug>:<symbol>` with the slug from the (canonical) rule id and the symbol reduced to its
    last dotted segment, so `useLive.onmessage` and `onmessage` are the same finding. Without a
    symbol the line stands in (distinct findings stay distinct, but the id moves with the code)."""
    raw = (result.get("fingerprints") or {}).get(FINGERPRINT_KEY)
    symbol = raw.split(":", 1)[-1].strip().split(".")[-1] if isinstance(raw, str) else ""
    named = bool(symbol)
    if not named:
        region = result["locations"][0]["physicalLocation"].get("region") or {}
        symbol = f"L{region.get('startLine', 0)}"
    return f"{result['ruleId'].rsplit('/', 1)[-1]}:{symbol}", named


def _result_path(result: Any) -> str | None:
    try:
        uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    except (KeyError, IndexError, TypeError):
        return None
    return uri.replace("\\", "/").removeprefix("./") if isinstance(uri, str) else None


def _extract_json(text: str) -> Any:
    """The answer may come wrapped in a code fence or with a sentence around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise SweepError("the agent's answer contains no JSON")
    try:
        return json.loads(text[start : end + 1])
    except ValueError as error:
        raise SweepError(f"the agent's answer is not valid JSON ({error})") from error
