from itertools import combinations

import pytest

from codeland_analyzer.layout import MARGIN, Rect, footprint_side, layout_city, slots_from_model

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


def assert_valid(districts: dict[str, Rect], buildings: dict[str, Rect]) -> None:
    for path, rect in buildings.items():
        assert contains(districts[path.rpartition("/")[0]], rect), path
    for path, rect in districts.items():
        if path:
            assert contains(districts[path.rpartition("/")[0]], rect), path
    for a, b in combinations(buildings.values(), 2):
        assert not overlaps(a, b)
    siblings: dict[str, list[Rect]] = {}
    for path, rect in districts.items():
        if path:
            siblings.setdefault(path.rpartition("/")[0], []).append(rect)
    for rects in siblings.values():
        for a, b in combinations(rects, 2):
            assert not overlaps(a, b)


def test_buildings_sit_inside_their_districts_without_overlapping():
    assert_valid(*layout_city(SIDES))


# --- stability across runs -------------------------------------------------------------------


def previous_of(districts: dict[str, Rect], buildings: dict[str, Rect]):
    """Slots as the analyzer would read them back from a written city model."""

    def entries(rects: dict[str, Rect]) -> list[dict]:
        return [{"path": path, "layout": rect.to_json()} for path, rect in rects.items()]

    return slots_from_model(entries(districts), entries(buildings))


def relative(districts: dict[str, Rect], buildings: dict[str, Rect], path: str) -> tuple:
    district = districts[path.rpartition("/")[0]]
    return buildings[path].x - district.x, buildings[path].z - district.z


def positions(buildings: dict[str, Rect]) -> dict[str, tuple[float, float]]:
    return {path: (round(r.x, 3), round(r.z, 3)) for path, r in buildings.items()}


def test_slots_are_read_back_from_the_model():
    districts, buildings = layout_city(SIDES)
    slots = previous_of(districts, buildings)

    assert set(slots) == {"", "src", "src/util", "test"}
    assert set(slots["src"]) == {"a.ts", "b.ts", "index.ts", "util"}
    x, z = relative(districts, buildings, "src/a.ts")
    assert slots["src"]["a.ts"] == pytest.approx((x - MARGIN, z - MARGIN))


def test_previous_layout_is_a_fixed_point():
    first = layout_city(SIDES)

    assert layout_city(SIDES, previous_of(*first)) == first


def test_new_file_is_appended_without_moving_its_neighbours():
    first = layout_city(SIDES)
    grown = SIDES | {"src/aaa.ts": 1.0}  # sorts first: a fresh layout would shift everything

    stable = layout_city(grown, previous_of(*first))
    fresh = layout_city(grown)

    assert_valid(*stable)
    existing = [p for p in SIDES if p.startswith("src/") and p.count("/") == 1]
    for path in existing:
        assert relative(*stable, path) == relative(*first, path), path
    assert any(relative(*fresh, p) != relative(*first, p) for p in existing)
    # The new building goes after every existing one in its district.
    new_x, new_z = relative(*stable, "src/aaa.ts")
    assert all((new_z, new_x) > relative(*first, p)[::-1] for p in existing)


def test_removed_files_leave_a_vacant_lot():
    first = layout_city(SIDES)
    removed = {p: s for p, s in SIDES.items() if p not in ("src/b.ts", "src/util/math.ts")}

    stable = layout_city(removed, previous_of(*first))

    assert_valid(*stable)
    before = positions(first[1])
    assert positions(stable[1]) == {path: before[path] for path in removed}
    # The vacancy is kept on the next run too (positions come from the model, not from order).
    again = layout_city(removed, previous_of(*stable))
    assert positions(again[1]) == positions(stable[1])


def test_growth_only_pushes_later_neighbours():
    first = layout_city(SIDES)
    grown = SIDES | {"src/a.ts": 4.0}

    stable = layout_city(grown, previous_of(*first))

    assert_valid(*stable)
    a_x, a_z = relative(*first, "src/a.ts")
    for path in SIDES:
        if path.startswith("src/") and path.count("/") == 1 and path != "src/a.ts":
            x, z = relative(*first, path)
            if (z, x) < (a_z, a_x):  # before the grown building: untouched
                assert relative(*stable, path) == (x, z), path
    assert relative(*stable, "src/a.ts") == (a_x, a_z)
