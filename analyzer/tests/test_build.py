import json
from pathlib import Path

import jsonschema

from codeland_analyzer.build import analyze
from codeland_analyzer.cli import main

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "schema" / "city-model.schema.json").read_text(encoding="utf-8")
)


def make_sample(repo):
    repo.write(".gitignore", "node_modules/\n")
    repo.write("node_modules/dep/index.ts", "export const ignored = 1;\n")
    repo.write("src/types.d.ts", "declare const x: number;\n")
    repo.write("src/util.ts", "export const twice = (n: number) => (n > 0 ? n * 2 : 0);\n")
    repo.write(
        "src/main.ts",
        'import { twice } from "./util";\nimport express from "express";\n'
        "export function run(n: number) {\n  if (n) {\n    return twice(n);\n  }\n  return 0;\n}\n",
    )
    # Many trivial callbacks: high summed complexity, but no branching logic.
    repo.write(
        "src/main.test.ts",
        'import { run } from "./main";\n'
        + "".join(f'it("case {i}", () => {{ run({i}); }});\n' for i in range(6)),
    )
    repo.commit()
    for path in ("src/main.ts", "src/main.test.ts"):
        repo.write(path, (repo.root / path).read_text() + "// touched\n")
    repo.commit()
    repo.write("src/draft.ts", "export {};\n")  # untracked, not ignored


def test_model_matches_schema_and_metrics(repo):
    make_sample(repo)
    coverage = repo.root / "lcov.info"
    coverage.write_text("SF:src/main.ts\nLF:4\nLH:1\nend_of_record\n", encoding="utf-8")

    model = analyze(repo.root, churn_days=30, coverage=coverage)

    jsonschema.validate(model, SCHEMA)
    buildings = {b["path"]: b for b in model["buildings"]}
    assert set(buildings) == {"src/main.ts", "src/main.test.ts", "src/util.ts", "src/draft.ts"}
    assert model["repository"]["branch"] == "main"
    assert model["edges"] == [
        {"from": "src/main.test.ts", "to": "src/main.ts", "kind": "import"},
        {"from": "src/main.ts", "to": "src/util.ts", "kind": "import"},
    ]
    assert buildings["src/main.test.ts"]["role"] == "test"
    assert buildings["src/main.ts"]["role"] == "source"

    main_metrics = buildings["src/main.ts"]["metrics"]
    assert main_metrics["imports"] == 2
    assert main_metrics["externalImports"] == 1
    assert main_metrics["churnCommits"] == 2
    assert main_metrics["coverage"] == 0.25
    assert main_metrics["decisions"] == 1
    assert main_metrics["hotspot"] == 1.0  # most branching and most changed
    test_metrics = buildings["src/main.test.ts"]["metrics"]
    assert test_metrics["complexity"] == 6
    assert test_metrics["decisions"] == 0
    assert test_metrics["hotspot"] == 0.0
    assert buildings["src/util.ts"]["metrics"]["hotspot"] == 0.5
    assert buildings["src/draft.ts"]["metrics"]["hotspot"] == 0.0
    assert buildings["src/util.ts"]["metrics"]["coverage"] is None
    assert {d["id"] for d in model["districts"]} == {".", "src"}


def test_cli_keeps_layout_stable_with_previous_model(repo, tmp_path):
    make_sample(repo)
    output = tmp_path / "city.json"
    assert main([str(repo.root), "-o", str(output), "--top", "0"]) == 0
    before = {b["path"]: b["layout"] for b in json.loads(output.read_text())["buildings"]}

    repo.write("src/aaa.ts", "export const first = 1;\n")  # would sort first in a fresh layout
    args = [str(repo.root), "-o", str(output), "--previous", str(output), "--top", "0"]
    assert main(args) == 0

    model = json.loads(output.read_text(encoding="utf-8"))
    jsonschema.validate(model, SCHEMA)
    after = {b["path"]: b["layout"] for b in model["buildings"]}
    assert set(after) == set(before) | {"src/aaa.ts"}
    assert {path: after[path] for path in before} == before


def test_cli_writes_model_and_lists_hotspots(repo, tmp_path, capsys):
    make_sample(repo)
    output = tmp_path / "city.json"

    assert main([str(repo.root), "-o", str(output), "--churn-days", "30"]) == 0

    jsonschema.validate(json.loads(output.read_text(encoding="utf-8")), SCHEMA)
    stderr = capsys.readouterr().err
    assert "4 files, 2 folders, 2 imports" in stderr
    assert "1.00  src/main.ts" in stderr
    assert "main.test.ts" not in stderr  # tests are left out of the ranking by default


def test_aliased_imports_become_edges_not_external(repo):
    repo.write(
        "tsconfig.json", '{"compilerOptions": {"baseUrl": ".", "paths": {"@lib/*": ["src/lib/*"]}}}'
    )
    repo.write("src/lib/util.ts", "export const x = 1;\n")
    repo.write("src/main.ts", 'import { x } from "@lib/util";\nimport "react";\nexport { x };\n')
    repo.commit()
    model = analyze(repo.root)
    assert {"from": "src/main.ts", "to": "src/lib/util.ts", "kind": "import"} in model["edges"]
    main = next(b for b in model["buildings"] if b["path"] == "src/main.ts")
    assert (main["metrics"]["imports"], main["metrics"]["externalImports"]) == (2, 1)
