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
