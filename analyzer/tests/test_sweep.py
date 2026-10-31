import json

import jsonschema
import pytest
from test_build import SCHEMA, make_sample

from codeland_analyzer.build import analyze
from codeland_analyzer.sarif import read_sarif
from codeland_analyzer.sweep import SweepError, normalize, sweep
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
        "agent/security/other-thing",
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
    with pytest.raises(SweepError, match="no TypeScript files"):
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
