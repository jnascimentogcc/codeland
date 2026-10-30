import pytest

from codeland_analyzer.churn import collect_churn, split_rename


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src/a.ts", ("src/a.ts", "src/a.ts")),
        ("a.ts => b.ts", ("a.ts", "b.ts")),
        ("src/{old => new}/a.ts", ("src/old/a.ts", "src/new/a.ts")),
        ("src/{ => sub}/a.ts", ("src/a.ts", "src/sub/a.ts")),
        ("src/{a.ts => b.ts}", ("src/a.ts", "src/b.ts")),
    ],
)
def test_split_rename(raw, expected):
    assert split_rename(raw) == expected


def test_churn_follows_renames(repo):
    repo.write("src/old.ts", "export const a = 1;\n")
    repo.commit()
    repo.write("src/old.ts", "export const a = 2;\nexport const b = 3;\n")
    repo.commit()
    (repo.root / "src" / "core").mkdir()
    repo.git("mv", "src/old.ts", "src/core/new.ts")
    repo.commit("rename")
    repo.write("src/core/new.ts", "export const a = 2;\nexport const b = 4;\n")
    repo.commit()

    churn = collect_churn(repo.root, days=30)

    assert set(churn) == {"src/core/new.ts"}
    assert churn["src/core/new.ts"].commits == 4
    # 1 added, then 1 deleted + 2 added, rename without changes, then 1 deleted + 1 added.
    assert churn["src/core/new.ts"].lines == 1 + 3 + 0 + 2


def test_churn_of_repository_without_commits(repo):
    assert collect_churn(repo.root, days=30) == {}
