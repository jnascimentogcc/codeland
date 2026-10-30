from codeland_analyzer.coverage import read_lcov


def test_read_lcov(tmp_path):
    repo = tmp_path / "repo"
    (repo / "coverage").mkdir(parents=True)
    report = repo / "coverage" / "lcov.info"
    absolute = (repo / "src" / "b.ts").resolve()
    report.write_text(
        "\n".join(
            [
                "TN:",
                "SF:src/a.ts",
                "LF:4",
                "LH:3",
                "end_of_record",
                f"SF:{absolute}",
                "DA:1,5",
                "DA:2,0",
                "end_of_record",
                "SF:../../elsewhere/c.ts",
                "LF:1",
                "LH:1",
                "end_of_record",
            ]
        ),
        encoding="utf-8",
    )

    assert read_lcov(report, repo) == {"src/a.ts": 0.75, "src/b.ts": 0.5}
