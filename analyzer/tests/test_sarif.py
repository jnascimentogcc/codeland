import json
from pathlib import Path

import jsonschema
import pytest
from test_build import SCHEMA, make_sample

from codeland_analyzer.build import analyze
from codeland_analyzer.cli import main
from codeland_analyzer.native import NativeThresholds, native_findings
from codeland_analyzer.sarif import SarifError, read_sarif

FIXTURES = Path(__file__).parent / "fixtures" / "sarif"


def fixture(repo, name: str) -> Path:
    """Copy a fixture next to the repository, pointing its %SRCROOT% at the real checkout."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    uri = repo.root.resolve().as_uri() + "/"
    target = repo.root.parent / name
    target.write_text(text.replace("REPO_URI", uri), encoding="utf-8")
    return target


def by_rule(findings):
    return {f["ruleId"]: f for f in findings}


def test_semgrep_report_maps_severity_category_and_paths(repo):
    make_sample(repo)
    imported = read_sarif(fixture(repo, "semgrep.sarif"), repo.root)

    xss, console = imported.findings
    assert (xss["category"], xss["severity"]) == ("security", "high")  # CWE tag, level error
    assert xss["location"] == {"path": "src/main.ts", "startLine": 4, "endLine": 5}
    assert xss["message"] == "Detected user input flowing into a response body. Escape it first."
    assert xss["title"] == "Detected user input flowing into a response body."
    assert xss["source"] == {"tool": "Semgrep OSS", "version": "1.99.0", "kind": "scanner"}
    assert (console["category"], console["severity"]) == ("maintainability", "low")
    assert console["location"]["path"] == "src/util.ts"  # "./" prefix removed
    assert console["location"]["endLine"] == 1
    assert imported.sources == [
        {
            "tool": "Semgrep OSS",
            "version": "1.99.0",
            "kind": "scanner",
            "file": "semgrep.sarif",
            "findings": 2,
            "dropped": 1,  # ../elsewhere/other.ts is outside the repository
        }
    ]


def test_codeql_report_uses_security_severity_base_ids_and_suppressions(repo):
    make_sample(repo)
    imported = read_sarif(fixture(repo, "codeql.sarif"), repo.root)

    findings = by_rule(imported.findings)
    sql = findings["js/sql-injection"]
    assert (sql["category"], sql["severity"]) == ("security", "high")  # 8.8 >= 7
    assert sql["location"]["path"] == "src/util.ts"  # resolved through originalUriBaseIds
    useless = findings["js/useless-assignment-to-local"]
    assert (useless["category"], useless["severity"], useless["status"]) == (
        "maintainability",
        "medium",
        "suppressed",
    )


def test_eslint_report_ids_duplicates_and_unlocated_results(repo):
    make_sample(repo)
    imported = read_sarif(fixture(repo, "eslint.sarif"), repo.root)

    unused, unused_again, eval_finding = imported.findings
    assert unused["category"] == "maintainability"  # tool default
    assert unused["id"] != unused_again["id"]  # same rule, file and message: counted twice
    assert unused_again["id"].startswith(unused["id"] + "-")
    assert eval_finding["category"] == "security"  # eslint-plugin-security prefix
    assert eval_finding["location"] == {
        "path": "package-lock.json",
        "startLine": None,
        "endLine": None,
    }
    assert imported.sources[0]["dropped"] == 1  # no location


def test_ids_survive_code_moving_inside_the_file(repo):
    make_sample(repo)
    report = fixture(repo, "codeql.sarif")
    first = by_rule(read_sarif(report, repo.root).findings)["js/sql-injection"]

    document = json.loads(report.read_text(encoding="utf-8"))
    result = document["runs"][0]["results"][0]
    result["locations"][0]["physicalLocation"]["region"] = {"startLine": 90}
    report.write_text(json.dumps(document), encoding="utf-8")
    second = by_rule(read_sarif(report, repo.root).findings)["js/sql-injection"]
    assert second["location"]["startLine"] == 90
    assert second["id"] == first["id"]

    # Without tool fingerprints the id comes from the snippet or message, still not the line.
    del result["partialFingerprints"]
    report.write_text(json.dumps(document), encoding="utf-8")
    third = by_rule(read_sarif(report, repo.root).findings)["js/sql-injection"]
    result["locations"][0]["physicalLocation"]["region"] = {"startLine": 2}
    report.write_text(json.dumps(document), encoding="utf-8")
    assert by_rule(read_sarif(report, repo.root).findings)["js/sql-injection"]["id"] == third["id"]


def test_absolute_file_uris_inside_the_repository_are_made_relative(repo):
    make_sample(repo)
    report = repo.root.parent / "abs.sarif"
    inside = (repo.root.resolve() / "src" / "util.ts").as_uri()
    outside = (repo.root.parent.resolve() / "outside.ts").as_uri()
    results = [
        {
            "ruleId": "r",
            "message": {"text": "m"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}],
        }
        for uri in (inside, outside)
    ]
    run = {"tool": {"driver": {"name": "t"}}, "results": results}
    report.write_text(json.dumps({"version": "2.1.0", "runs": [run]}), encoding="utf-8")

    imported = read_sarif(report, repo.root)

    assert [f["location"]["path"] for f in imported.findings] == ["src/util.ts"]
    assert imported.sources[0]["dropped"] == 1


def test_container_paths_placeholder_fingerprints_and_linter_errors(repo):
    """What Semgrep in Docker and ESLint really emit."""
    make_sample(repo)
    report = repo.root.parent / "real.sarif"

    def result(rule, uri, level, line):
        return {
            "ruleId": rule,
            "level": level,
            "message": {"text": "m"},
            "fingerprints": {"matchBasedId/v1": "requires login"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": uri, "uriBaseId": "%SRCROOT%"},
                        "region": {"startLine": line, "snippet": {"text": f"code {line}"}},
                    }
                }
            ],
        }

    results = [
        result("sg.a", "/src/src/util.ts", "error", 1),  # repo mounted at /src
        result("sg.a", "/src/src/util.ts", "error", 2),
        result("sg.a", "/etc/passwd", "error", 1),
        result("sg.a", "/home/runner/work/x/x/src/../../../../etc/hosts", "error", 1),
        result("no-var", "src/main.ts", "error", 3),
    ]
    run = {
        "tool": {
            "driver": {
                "name": "ESLint",
                "rules": [{"id": "no-var"}, {"id": "sg.a", "properties": {"tags": ["security"]}}],
            }
        },
        "results": results,
    }
    report.write_text(json.dumps({"version": "2.1.0", "runs": [run]}), encoding="utf-8")

    imported = read_sarif(report, repo.root)

    paths = [f["location"]["path"] for f in imported.findings]
    assert paths == ["src/util.ts", "src/util.ts", "src/main.ts"]
    assert imported.sources[0]["dropped"] == 2
    first, second, linter = imported.findings
    assert first["id"] != second["id"]  # the placeholder fingerprint does not merge them
    assert (linter["category"], linter["severity"]) == ("maintainability", "medium")
    assert first["severity"] == "high"  # level error outside maintainability stays high


@pytest.mark.parametrize("content", ['{"version": "2.0.0", "runs": []}', "not json", "[]"])
def test_unsupported_or_broken_files_fail_clearly(repo, content):
    report = repo.root.parent / "bad.sarif"
    report.write_text(content, encoding="utf-8")
    with pytest.raises(SarifError, match="bad.sarif"):
        read_sarif(report, repo.root)


def test_native_findings_follow_the_thresholds(repo):
    make_sample(repo)
    model = analyze(repo.root, churn_days=30, native=None)
    assert model["findings"] == []

    strict = NativeThresholds(max_decisions=1, min_hotspot=0.6, min_hotspot_decisions=1)
    findings = native_findings(model["buildings"], strict)
    found = {(f["ruleId"], f["location"]["path"]) for f in findings}
    assert found == {
        ("codeland/high-complexity", "src/main.ts"),
        ("codeland/high-complexity", "src/util.ts"),  # one ternary is one decision
        ("codeland/hotspot", "src/main.ts"),  # util.ts only reaches 0.5
    }  # test files never produce native findings

    assert native_findings(model["buildings"], NativeThresholds()) == []


def test_model_with_findings_matches_schema_and_is_deterministic(repo, tmp_path, capsys):
    make_sample(repo)
    coverage = repo.root / "lcov.info"
    coverage.write_text("SF:src/main.ts\nLF:4\nLH:1\nend_of_record\n", encoding="utf-8")
    output = tmp_path / "city.json"
    args = [str(repo.root), "-o", str(output), "--churn-days", "30", "--top", "0"]
    args += ["--coverage", str(coverage), "--max-decisions", "1"]
    for name in ("semgrep.sarif", "codeql.sarif"):
        args += ["--sarif", str(fixture(repo, name))]

    assert main(args) == 0
    first = json.loads(output.read_text(encoding="utf-8"))
    assert main(args) == 0
    second = json.loads(output.read_text(encoding="utf-8"))

    jsonschema.validate(first, SCHEMA)
    assert [f["id"] for f in first["findings"]] == [f["id"] for f in second["findings"]]
    paths = [(f["location"]["path"], f["location"]["startLine"] or 0) for f in first["findings"]]
    assert paths == sorted(paths)
    assert {s["tool"] for s in first["analysis"]["findingSources"]} == {
        "Semgrep OSS",
        "CodeQL",
        "codeland",
    }
    rules = {f["ruleId"] for f in first["findings"]}
    assert {"codeland/high-complexity", "codeland/low-coverage"} <= rules
    assert "findings: Semgrep OSS 2, 1 ignored" in capsys.readouterr().err


def test_cli_rejects_non_sarif_2_1(repo, tmp_path, capsys):
    make_sample(repo)
    report = tmp_path / "old.sarif"
    report.write_text('{"version": "1.0.0"}', encoding="utf-8")
    assert main([str(repo.root), "--sarif", str(report), "--top", "0"]) == 2
    assert "only SARIF 2.1.0" in capsys.readouterr().err
