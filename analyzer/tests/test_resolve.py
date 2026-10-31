import pytest

from codeland_analyzer.resolve import resolve

KNOWN = {"src/a.ts", "src/view.tsx", "src/util/index.ts", "src/esm.ts", "lib/b.ts"}


@pytest.mark.parametrize(
    ("specifier", "expected"),
    [
        ("./a", "src/a.ts"),
        ("./a.ts", "src/a.ts"),
        ("./view", "src/view.tsx"),
        ("./util", "src/util/index.ts"),
        ("./esm.js", "src/esm.ts"),
        ("../lib/b", "lib/b.ts"),
        ("./missing", None),
        ("../../outside", None),
        ("react", None),
        ("@scope/pkg", None),
    ],
)
def test_resolve(specifier, expected):
    assert resolve("src/main.ts", specifier, KNOWN) == expected


def _configs(tmp_path, files: dict[str, str]):
    from codeland_analyzer.resolve import load_tsconfigs

    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return load_tsconfigs(tmp_path, sorted(n for n in files if n.endswith("tsconfig.json")))


def test_paths_with_wildcards_comments_and_trailing_commas(tmp_path):
    configs = _configs(
        tmp_path,
        {
            "tsconfig.json": """{
              // aliases
              "compilerOptions": {
                "baseUrl": ".",
                "paths": {"@app/*": ["src/app/*"], "@util": ["src/util/index.ts"],},
              },
            }""",
        },
    )
    known = {"src/app/a.ts", "src/util/index.ts", "src/x.ts", "src/main.ts"}
    assert resolve("src/main.ts", "@app/a", known, configs) == "src/app/a.ts"
    assert resolve("src/main.ts", "@util", known, configs) == "src/util/index.ts"
    assert resolve("src/main.ts", "src/x", known, configs) == "src/x.ts"  # bare via baseUrl
    assert resolve("src/main.ts", "@app/missing", known, configs) is None
    assert resolve("src/main.ts", "react", known, configs) is None


def test_longest_prefix_wins_and_paths_without_base_url_are_relative_to_the_config(tmp_path):
    configs = _configs(
        tmp_path,
        {
            "tsconfig.json": (
                '{"compilerOptions": {"paths": {"@/*": ["src/*"], "@/gen/*": ["gen/*"]}}}'
            )
        },
    )
    known = {"src/a.ts", "gen/b.ts"}
    assert resolve("src/main.ts", "@/a", known, configs) == "src/a.ts"
    assert resolve("src/main.ts", "@/gen/b", known, configs) == "gen/b.ts"
    assert resolve("src/main.ts", "src/a", known, configs) is None  # no baseUrl: not a lookup root


def test_extends_and_nested_configs(tmp_path):
    configs = _configs(
        tmp_path,
        {
            "tsconfig.base.json": (
                '{"compilerOptions": {"baseUrl": ".", "paths": {"@core/*": ["core/*"]}}}'
            ),
            "tsconfig.json": '{"extends": "./tsconfig.base"}',
            "web/tsconfig.json": '{"compilerOptions": {"baseUrl": "src", "paths": {"~/*": ["*"]}}}',
        },
    )
    known = {"core/c.ts", "web/src/v.ts", "web/src/main.ts"}
    assert resolve("tools/x.ts", "@core/c", known, configs) == "core/c.ts"  # inherited from base
    assert resolve("web/src/main.ts", "~/v", known, configs) == "web/src/v.ts"  # nearest config
    assert resolve("web/src/main.ts", "v", known, configs) == "web/src/v.ts"  # its own baseUrl
    assert resolve("web/src/main.ts", "@core/c", known, configs) is None  # not inherited there


def test_broken_tsconfig_is_ignored(tmp_path):
    assert _configs(tmp_path, {"tsconfig.json": "{not json"}) == []
