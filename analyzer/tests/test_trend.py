import jsonschema
import pytest
from test_build import SCHEMA, make_sample
from test_sarif import fixture

from codeland_analyzer.build import analyze
from codeland_analyzer.triage import TriageError, apply_triage, read_triage, write_triage
from codeland_analyzer.triage_cli import main as triage_main


def scan(repo, previous=None, **kwargs):
    return analyze(
        repo.root,
        churn_days=30,
        sarif=[fixture(repo, "semgrep.sarif")],
        native=None,
        previous=previous,
        **kwargs,
    )


def test_first_model_has_no_trend_and_every_finding_is_first_seen_now(repo):
    make_sample(repo)
    model = scan(repo)
    assert model["analysis"]["trend"] is None
    assert {f["firstSeen"] for f in model["findings"]} == {model["generatedAt"]}
    jsonschema.validate(model, SCHEMA)


def test_trend_carries_first_seen_and_lists_fixed_findings(repo):
    make_sample(repo)
    first = scan(repo)
    first["generatedAt"] = "2020-01-01T00:00:00+00:00"
    for finding in first["findings"]:
        finding["firstSeen"] = "2019-06-01T00:00:00+00:00"
    gone = dict(first["findings"][0], id="gone", ruleId="old.rule")
    first["findings"].append(gone)

    second = scan(repo, previous=first)

    trend = second["analysis"]["trend"]
    assert trend["since"] == "2020-01-01T00:00:00+00:00"
    assert [f["id"] for f in trend["fixed"]] == ["gone"]
    assert {f["firstSeen"] for f in second["findings"]} == {"2019-06-01T00:00:00+00:00"}
    jsonschema.validate(second, SCHEMA)


def test_a_tool_that_did_not_report_this_time_is_not_counted_as_fixed(repo):
    make_sample(repo)
    first = scan(repo)
    second = analyze(repo.root, churn_days=30, native=None, previous=first)  # no SARIF at all
    assert second["analysis"]["trend"]["fixed"] == []


def test_triage_is_applied_by_id_and_reports_stale_entries(repo):
    make_sample(repo)
    model = scan(repo)
    target = model["findings"][0]["id"]
    file = repo.root.parent / "triage.json"
    write_triage(file, {target: {"state": "accepted", "note": "legacy", "at": "2026-01-02"}})
    write_triage(
        file,
        {**read_triage(file), "deadbeef": {"state": "false-positive", "note": None, "at": None}},
    )

    triaged = scan(repo, triage=file)

    assert triaged["analysis"]["triageSource"] == file.as_posix()
    by_id = {f["id"]: f for f in triaged["findings"]}
    assert by_id[target]["triage"] == {"state": "accepted", "note": "legacy", "at": "2026-01-02"}
    assert all("triage" not in f for i, f in by_id.items() if i != target)
    assert apply_triage(triaged["findings"], read_triage(file)) == ["deadbeef"]
    jsonschema.validate(triaged, SCHEMA)


def test_triage_cli_records_and_reopens_decisions(tmp_path):
    file = tmp_path / "t.json"
    assert triage_main([str(file), "accepted", "a1", "b2", "--note", "known"]) == 0
    assert triage_main([str(file), "false-positive", "c3"]) == 0
    assert triage_main([str(file), "reopen", "a1"]) == 0
    entries = read_triage(file)
    assert set(entries) == {"b2", "c3"}
    assert entries["b2"]["note"] == "known"
    assert entries["c3"]["state"] == "false-positive"
    assert triage_main([str(file), "accepted"]) == 2  # no ids


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"version": 2, "findings": {}}',
        '{"version": 1, "findings": {"a": {"state": "x"}}}',
    ],
)
def test_broken_triage_files_fail_clearly(tmp_path, content):
    file = tmp_path / "t.json"
    file.write_text(content, encoding="utf-8")
    with pytest.raises(TriageError, match="t.json"):
        read_triage(file)
