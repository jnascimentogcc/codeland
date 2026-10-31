"""codeland-sweep: runs a read-only Claude Code session over a repository and turns its answer into
a SARIF report that follows the sweep agent contract (docs 6.8)."""

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeland_analyzer.gitrepo import list_source_files
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


class SweepError(Exception):
    pass


# (prompt, repo, model, budget in USD) -> the agent's final answer
Agent = Callable[[str, Path, str, float], str]


@dataclass
class SweepReport:
    document: dict[str, Any]
    results: int
    dropped: int = 0
    notes: list[str] = field(default_factory=list)


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
        raise SweepError("the `claude` CLI (Claude Code) was not found on PATH")
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
) -> SweepReport:
    """Runs the agent and returns a normalized SARIF document (see `normalize`)."""
    if kind not in KINDS:
        raise SweepError(f"unknown kind {kind!r}; choose one of {', '.join(KINDS)}")
    repo = repo.resolve()
    files = [p for p in list_source_files(repo) if not paths or any(p.startswith(x) for x in paths)]
    if not files:
        raise SweepError("no TypeScript files in scope")
    prompt = build_prompt(kind, files)
    reports = [
        normalize((agent or run_claude)(prompt, repo, model, budget), kind, model, set(files))
        for _ in range(max(runs, 1))
    ]
    return reports[0] if len(reports) == 1 else merge(reports)


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
        unique.setdefault(result["fingerprints"][FINGERPRINT_KEY], result)
    dropped += len(kept) - len(unique)  # the same slug and symbol twice is one finding
    kept = list(unique.values())

    driver = run.setdefault("tool", {}).setdefault("driver", {})
    driver["name"] = f"claude-code-sweep-{kind}"
    driver["semanticVersion"] = model
    driver["properties"] = {**(driver.get("properties") or {}), KIND_PROPERTY: "agent"}
    described = {
        _rule_id(kind, rule["id"]): rule
        for rule in driver.get("rules") or []
        if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }
    driver["rules"] = [
        {**described.get(rule_id, {}), "id": rule_id}
        for rule_id in sorted({r["ruleId"] for r in kept})
    ]
    run["results"] = kept
    document["version"] = "2.1.0"
    document["runs"] = [run]
    return SweepReport(document, len(kept), dropped, notes)


def merge(reports: list[SweepReport]) -> SweepReport:
    """Union of several runs by finding identity: one session can miss what the next one finds."""
    first = reports[0]
    run = first.document["runs"][0]
    seen: dict[str, dict[str, Any]] = {}
    for report in reports:
        for result in report.document["runs"][0]["results"]:
            seen.setdefault(result["fingerprints"][FINGERPRINT_KEY], result)
    run["results"] = list(seen.values())[:MAX_RESULTS]
    rules = {
        r["id"]: r for rep in reports for r in rep.document["runs"][0]["tool"]["driver"]["rules"]
    }
    run["tool"]["driver"]["rules"] = [
        rules[i] for i in sorted({r["ruleId"] for r in run["results"]})
    ]
    notes = sorted({n for report in reports for n in report.notes})
    dropped = sum(r.dropped for r in reports)
    return SweepReport(first.document, len(run["results"]), dropped, notes)


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
