import json

import jsonschema
import pytest
from test_build import SCHEMA, make_sample

from codeland_analyzer.build import analyze
from codeland_analyzer.gitrepo import list_source_files
from codeland_analyzer.sarif import read_sarif
from codeland_analyzer.sweep import AgentUnavailable, SweepError, normalize, sweep
from codeland_analyzer.sweep_cli import main

FILES = {"src/main.ts", "src/util.ts"}


def answer(*results, extra=None):
    document = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "whatever", "rules": [{"id": "Command_Injection"}]}},
                "results": list(results),
                **(extra or {}),
            }
        ],
    }
    return json.dumps(document)


def result(rule, uri, line=1, fingerprint=None):
    item = {
        "ruleId": rule,
        "level": "error",
        "message": {"text": "bad"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": line, "snippet": {"text": "code"}},
                }
            }
        ],
    }
    if fingerprint:
        item["fingerprints"] = {"codeland/finding/v1": fingerprint}
    return item


def test_normalize_enforces_the_contract():
    text = (
        "Here is the report:\n```json\n"
        + answer(
            result("Command_Injection", "./src/main.ts", fingerprint="command-injection:run"),
            result("security/other-thing", "src/util.ts"),
            result("x", "src/missing.ts"),  # not in scope
            {"message": {"text": "no rule"}},
        )
        + "\n```"
    )

    report = normalize(text, "security", "claude-test", FILES)

    assert (report.results, report.dropped) == (2, 2)
    run = report.document["runs"][0]
    driver = run["tool"]["driver"]
    assert driver["name"] == "claude-code-sweep-security"
    assert driver["semanticVersion"] == "claude-test"
    assert driver["properties"]["codeland/kind"] == "agent"
    assert [r["ruleId"] for r in run["results"]] == [
        "agent/security/command-injection",
        "agent/security/other",  # outside the closed vocabulary
    ]
    assert [r["id"] for r in driver["rules"]] == [r["ruleId"] for r in run["results"]]
    assert len(report.notes) == 1  # one result without a fingerprint


@pytest.mark.parametrize("text", ["no json here", "{not json}", '{"version": "2.1.0"}'])
def test_unusable_answers_fail_clearly(text):
    with pytest.raises(SweepError):
        normalize(text, "security", "m", FILES)


def test_sweep_prompts_the_agent_with_the_scope_and_imports_cleanly(repo):
    make_sample(repo)
    seen = {}

    def agent(prompt, cwd, model, budget):
        seen.update(prompt=prompt, cwd=cwd, model=model, budget=budget)
        return answer(result("injection", "src/main.ts", 4, "injection:handler"))

    report = sweep(repo.root, "security", agent=agent, model="m1", budget=0.5, paths=["src/"])

    assert seen["cwd"] == repo.root.resolve()
    assert (seen["model"], seen["budget"]) == ("m1", 0.5)
    assert "- src/main.ts" in seen["prompt"]
    assert "codeland/finding/v1" in seen["prompt"]
    path = repo.root.parent / "sweep.sarif"
    path.write_text(json.dumps(report.document), encoding="utf-8")
    imported = read_sarif(path, repo.root)
    (finding,) = imported.findings
    assert (finding["source"]["kind"], finding["category"]) == ("agent", "security")


def test_unknown_kind_and_empty_scope_are_rejected(repo):
    make_sample(repo)
    with pytest.raises(SweepError, match="unknown kind"):
        sweep(repo.root, "vibes", agent=lambda *a: "")
    with pytest.raises(SweepError, match="no TypeScript or Python files"):
        sweep(repo.root, "security", agent=lambda *a: "", paths=["nowhere/"])


def test_cli_writes_the_sarif_and_reanalyzes_the_city(repo, monkeypatch, tmp_path):
    make_sample(repo)
    monkeypatch.setattr(
        "codeland_analyzer.sweep.run_claude",
        lambda *a: answer(result("injection", "src/main.ts", 4, "injection:handler")),
    )
    sarif = tmp_path / "out.sarif"
    city = tmp_path / "city.json"
    first = analyze(repo.root, churn_days=30, native=None)
    city.write_text(json.dumps(first), encoding="utf-8")

    code = main([str(repo.root), "--kind", "security", "-o", str(sarif), "--city", str(city)])

    assert code == 0
    model = json.loads(city.read_text(encoding="utf-8"))
    jsonschema.validate(model, SCHEMA)
    (agent_finding,) = [f for f in model["findings"] if f["source"]["kind"] == "agent"]
    assert agent_finding["location"]["path"] == "src/main.ts"
    assert model["analysis"]["trend"] is not None  # the old city file was the --previous model
    assert sarif.exists()


def test_slugs_are_canonical_and_symbols_are_reduced_so_ids_survive_rewording():
    first = normalize(
        answer(
            result("untrusted-websocket-url", "src/main.ts", 3, "untrusted-url:useLive.liveUrl")
        ),
        "security",
        "m",
        FILES,
    )
    second = normalize(
        answer(result("Untrusted_Input", "src/main.ts", 9, "untrusted-input:liveUrl")),
        "security",
        "m",
        FILES,
    )
    # "untrusted-websocket-url" is not in the vocabulary; "untrusted-input" is.
    a = first.document["runs"][0]["results"][0]
    b = second.document["runs"][0]["results"][0]
    assert a["fingerprints"]["codeland/finding/v1"] == "other:liveUrl"
    assert b["fingerprints"]["codeland/finding/v1"] == "untrusted-input:liveUrl"
    assert (
        normalize(
            answer(
                result("untrusted-input", "src/main.ts", 3, "x:a.liveUrl"),
                result("untrusted-input", "src/main.ts", 9, "y:liveUrl"),
            ),
            "security",
            "m",
            FILES,
        ).results
        == 1
    )  # same slug and symbol twice is one finding


def test_runs_are_merged_by_finding_identity(repo):
    make_sample(repo)
    replies = iter(
        [
            answer(result("injection", "src/main.ts", 4, "injection:a")),
            answer(),  # a run that finds nothing
            answer(
                result("injection", "src/main.ts", 4, "injection:a"),
                result("command-injection", "src/util.ts", 1, "x:b"),
            ),
        ]
    )

    report = sweep(repo.root, "security", agent=lambda *a: next(replies), runs=3)

    run = report.document["runs"][0]
    assert report.results == 2
    assert [r["ruleId"] for r in run["results"]] == [
        "agent/security/other",
        "agent/security/command-injection",
    ]
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == sorted(
        {r["ruleId"] for r in run["results"]}
    )


def test_chunks_split_the_scope_and_a_failed_session_does_not_lose_the_rest(repo):
    make_sample(repo)
    prompts = []

    def agent(prompt, cwd, model, budget):
        prompts.append(prompt)
        if "- src/util.ts\n" in prompt:
            raise SweepError("claude failed")
        return answer(result("injection", "src/main.ts", 4, "injection:a"))

    report = sweep(repo.root, "security", agent=agent, chunk=1)

    sessions = len(prompts)
    files = len(list_source_files(repo.root))
    assert sessions == files + 1  # the failing session was tried twice
    assert all(sum(line.startswith("- src/") for line in p.splitlines()) == 1 for p in prompts)
    assert report.results == 1  # only the session that had main.ts in scope keeps the result
    assert report.notes == [f"1 of {files} sessions failed: claude failed"]
    with pytest.raises(SweepError, match="boom"):
        sweep(repo.root, "security", agent=lambda *a: (_ for _ in ()).throw(SweepError("boom")))


def test_a_bare_string_message_is_corrected_and_the_importer_tolerates_it(repo):
    make_sample(repo)
    item = result("injection", "src/main.ts", 4, "injection:a")
    item["message"] = "plain text instead of an object"

    report = normalize(answer(item), "security", "m", FILES)

    assert report.document["runs"][0]["results"][0]["message"] == {
        "text": "plain text instead of an object"
    }
    path = repo.root.parent / "bare.sarif"
    path.write_text(answer(item), encoding="utf-8")  # raw, uncorrected
    (finding,) = read_sarif(path, repo.root).findings
    assert finding["message"] == "plain text instead of an object"


def per_file_agent(calls, skip=()):
    """One finding per file listed in the prompt; records which files each session received."""

    def agent(prompt, cwd, model, budget):
        listed = [line[2:] for line in prompt.splitlines() if line.startswith("- src/")]
        calls.append(listed)
        if any(path in skip for path in listed):
            raise SweepError("claude failed")
        name = lambda p: p.rsplit("/", 1)[-1].replace(".", "_")  # noqa: E731
        return answer(
            *(result("command-injection", p, 1, f"command-injection:{name(p)}") for p in listed)
        )

    return agent


def keys(report):
    return {r["fingerprints"]["codeland/finding/v1"] for r in report.document["runs"][0]["results"]}


def test_incremental_sweep_reviews_only_changed_files_and_replaces_their_findings(repo):
    make_sample(repo)
    calls = []
    first = sweep(repo.root, "security", agent=per_file_agent(calls))
    everything = calls[0]
    assert first.swept == first.total == len(everything)

    calls.clear()
    unchanged = sweep(repo.root, "security", agent=per_file_agent(calls), previous=first.document)
    assert calls == [] and unchanged.swept == 0  # nothing changed: the agent is not called
    assert keys(unchanged) == keys(first)

    repo.write("src/util.ts", "export const twice = (n: number) => n * 2; // edited\n")
    quiet = lambda *a: answer()  # noqa: E731  (the edited file no longer has a problem)
    second = sweep(repo.root, "security", agent=quiet, previous=first.document)
    assert second.swept == 1
    assert keys(second) == keys(first) - {
        "command-injection:util_ts"
    }  # replaced, others carried over

    repo.write("src/util.ts", "export const twice = (n: number) => n * 3; // edited again\n")
    calls.clear()
    third = sweep(repo.root, "security", agent=per_file_agent(calls), previous=second.document)
    assert calls == [["src/util.ts"]]
    assert keys(third) == keys(first)


def test_files_of_a_failed_session_are_retried_and_other_state_is_ignored(repo):
    make_sample(repo)
    calls = []
    first = sweep(repo.root, "security", agent=per_file_agent(calls, skip={"src/util.ts"}), chunk=1)
    assert first.notes and "failed" in first.notes[0]

    calls.clear()
    second = sweep(
        repo.root, "security", agent=per_file_agent(calls), chunk=1, previous=first.document
    )
    assert calls == [["src/util.ts"]]  # only the file that failed is reviewed again
    assert "command-injection:util_ts" in keys(second)

    calls.clear()  # a report of another kind, or of an older prompt version, is not resumed
    sweep(repo.root, "reliability", agent=per_file_agent(calls), previous=second.document)
    assert len(calls[0]) == len(list_source_files(repo.root))
    stale = json.loads(json.dumps(second.document))
    stale["runs"][0]["properties"]["codeland/sweep"]["version"] = 0
    calls.clear()
    sweep(repo.root, "security", agent=per_file_agent(calls), previous=stale)
    assert len(calls[0]) == len(list_source_files(repo.root))


def test_cli_incremental_reads_the_existing_output(repo, monkeypatch, tmp_path):
    make_sample(repo)
    calls = []
    monkeypatch.setattr("codeland_analyzer.sweep.run_claude", per_file_agent(calls))
    sarif = tmp_path / "out.sarif"
    args = [str(repo.root), "--kind", "security", "-o", str(sarif), "--incremental"]

    assert main(args) == 0 and len(calls) == 1
    assert main(args) == 0 and len(calls) == 1  # unchanged: no new session
    repo.write("src/util.ts", "export const twice = (n: number) => n * 4; // edited\n")
    assert main(args) == 0 and calls[-1] == ["src/util.ts"]


def test_a_bad_answer_is_retried_once_but_a_missing_cli_is_not(repo):
    make_sample(repo)
    answers = iter(
        ["not sarif at all", answer(result("command-injection", "src/main.ts", 4, "x:a"))]
    )
    report = sweep(repo.root, "security", agent=lambda *a: next(answers))
    assert report.results == 1 and not report.notes

    calls = []

    def always_bad(*a):
        calls.append(1)
        return "still not sarif"

    with pytest.raises(SweepError):
        sweep(repo.root, "security", agent=always_bad)
    assert len(calls) == 2

    def missing(*a):
        calls.append(1)
        raise AgentUnavailable("no claude")

    calls.clear()
    with pytest.raises(AgentUnavailable):
        sweep(repo.root, "security", agent=missing)
    assert len(calls) == 1
