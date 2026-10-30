import pytest

from codeland_analyzer.gitrepo import is_test


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/main.ts", False),
        ("src/main.test.ts", True),
        ("src/view.spec.tsx", True),
        ("tests/helpers.ts", True),
        ("packages/core/__tests__/a.ts", True),
        ("src/testing/fixtures.ts", False),
        ("src/latest.ts", False),
    ],
)
def test_is_test(path, expected):
    assert is_test(path) is expected
