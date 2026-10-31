from codeland_analyzer.dedupe import mark_duplicates


def finding(
    id, tool, path="a.ts", lines=(5, 5), category="security", severity="high", kind="scanner"
):
    return {
        "id": id,
        "category": category,
        "severity": severity,
        "location": {"path": path, "startLine": lines[0], "endLine": lines[1]},
        "source": {"tool": tool, "version": None, "kind": kind},
    }


def marks(*findings):
    mark_duplicates(list(findings))
    return {f["id"]: f["duplicateOf"] for f in findings}


def test_two_tools_on_the_same_lines_collapse_onto_the_more_severe_one():
    result = marks(
        finding("agent", "sweep", kind="agent", severity="critical"),
        finding("scan", "semgrep", severity="high"),
    )
    assert result == {"agent": None, "scan": "agent"}


def test_ties_prefer_scanner_over_agent_and_ranges_must_overlap():
    result = marks(
        finding("agent", "sweep", kind="agent", lines=(8, 8)),
        finding("scan", "semgrep", lines=(6, 8)),
        finding("next", "semgrep", lines=(9, 9)),  # same tool as scan; no overlap anyway
    )
    assert result == {"agent": "scan", "scan": None, "next": None}


def test_different_file_category_or_adjacent_lines_are_not_duplicates():
    result = marks(
        finding("a", "t1"),
        finding("other-file", "t2", path="b.ts"),
        finding("other-category", "t2", category="reliability"),
        finding("adjacent", "t2", lines=(6, 6)),
    )
    assert set(result.values()) == {None}


def test_one_tool_never_merges_its_own_findings_and_chains_do_not_hide_findings():
    result = marks(
        finding("a1", "eslint", lines=(15, 15), severity="medium"),
        finding("a2", "eslint", lines=(15, 15), severity="medium"),
        finding("agent", "sweep", kind="agent", lines=(15, 15), severity="high"),
    )
    # Both lint findings repeat the agent's, but never each other.
    assert result == {"agent": None, "a1": "agent", "a2": "agent"}


def test_findings_without_lines_are_never_duplicates():
    result = marks(
        finding("lock1", "t1", lines=(None, None)),
        finding("lock2", "t2", lines=(None, None)),
    )
    assert set(result.values()) == {None}
