from itertools import combinations

from codeland_analyzer.layout import Rect, footprint_side, layout_city

SIDES = {
    "README.ts": 1.0,
    "src/index.ts": footprint_side(9),
    "src/a.ts": footprint_side(1),
    "src/b.ts": footprint_side(0),
    "src/util/math.ts": footprint_side(4),
    "src/util/str.ts": 1.0,
    "test/a.test.ts": 2.0,
}


def overlaps(a: Rect, b: Rect) -> bool:
    return (
        a.x < b.x + b.width and b.x < a.x + a.width and a.z < b.z + b.depth and b.z < a.z + a.depth
    )


def contains(outer: Rect, inner: Rect) -> bool:
    return (
        outer.x <= inner.x
        and outer.z <= inner.z
        and inner.x + inner.width <= outer.x + outer.width
        and inner.z + inner.depth <= outer.z + outer.depth
    )


def test_few_large_children_do_not_stack_into_a_strip():
    # Shape of a real repo: two big folders side by side used to end up one per row.
    sides = {f"src/{d}/f{i}.ts": 2.0 for d in ("api", "domain", "repos") for i in range(6)}
    sides |= {f"tests/t{i}.test.ts": 2.0 for i in range(12)}
    sides["vitest.config.ts"] = 1.0

    districts, _ = layout_city(sides)

    for path, rect in districts.items():
        assert max(rect.width, rect.depth) / min(rect.width, rect.depth) <= 2, path


def test_layout_is_deterministic():
    assert layout_city(SIDES) == layout_city(dict(reversed(SIDES.items())))


def test_every_folder_and_file_is_placed():
    districts, buildings = layout_city(SIDES)

    assert set(districts) == {"", "src", "src/util", "test"}
    assert set(buildings) == set(SIDES)
    assert all(buildings[p].width == SIDES[p] for p in SIDES)


def test_buildings_sit_inside_their_districts_without_overlapping():
    districts, buildings = layout_city(SIDES)

    for path, rect in buildings.items():
        folder = path.rpartition("/")[0]
        assert contains(districts[folder], rect), path
    for a, b in combinations(buildings.values(), 2):
        assert not overlaps(a, b)
    for name in ("src/util", "test"):
        assert contains(districts["src" if name == "src/util" else ""], districts[name])
    assert not overlaps(districts["src"], districts["test"])
