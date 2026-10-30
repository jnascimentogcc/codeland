"""Deterministic city layout: folders become nested districts, files become buildings.

Each district shelf-packs its children (sub-districts and buildings) into rows.

* Without a previous layout, children are sorted by name and the row width is chosen to keep the
  district close to square.
* With a previous layout (docs/architecture_and_mvp.md section 2.3), every child keeps its previous
  position inside its district. Removed children leave a vacant lot (nothing slides into the gap),
  new children are appended after the existing ones, and only growth pushes things: a wider child
  pushes the later children of its row, a deeper row pushes the rows below. Vacant lots accumulate;
  running without a previous layout re-plans the city compactly.
"""

import math
import posixpath
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

STREET = 1.0  # gap between items inside a district
MARGIN = 1.0  # border between a district's edge and its content
_ROW_TOLERANCE = 1e-3

Placer = Callable[[float, float], None]
Item = tuple[str, float, float, Placer]  # child name, width, depth, placer
Rows = list[list[Item]]
Offsets = list[tuple[float, float, Placer]]
# folder path -> child name -> (x, z) of the child relative to the district's content origin
PreviousSlots = dict[str, dict[str, tuple[float, float]]]


@dataclass(frozen=True)
class Rect:
    x: float
    z: float
    width: float
    depth: float

    def to_json(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in vars(self).items()}


@dataclass
class _Folder:
    folders: dict[str, "_Folder"] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)  # name -> repository path


def footprint_side(imports: int) -> float:
    """Building side length; area grows linearly with efferent coupling."""
    return 1.0 + math.sqrt(imports)


def layout_city(
    sides: dict[str, float], previous: PreviousSlots | None = None
) -> tuple[dict[str, Rect], dict[str, Rect]]:
    """sides: file path -> building side. Returns (district rects by folder, building rects)."""
    root = _Folder()
    for path in sides:
        *folders, name = path.split("/")
        node = root
        for folder in folders:
            node = node.folders.setdefault(folder, _Folder())
        node.files[name] = path

    districts: dict[str, Rect] = {}
    buildings: dict[str, Rect] = {}
    _, _, place = _pack(root, "", sides, previous or {}, districts, buildings)
    place(0.0, 0.0)
    return districts, buildings


def slots_from_model(
    districts: Iterable[Mapping[str, Any]], buildings: Iterable[Mapping[str, Any]]
) -> PreviousSlots:
    """Each child's position relative to its district, read back from a city model."""
    districts = list(districts)
    origins = {d["path"]: (d["layout"]["x"] + MARGIN, d["layout"]["z"] + MARGIN) for d in districts}
    slots: PreviousSlots = defaultdict(dict)
    for entry in [*districts, *buildings]:
        path = entry["path"]
        parent = posixpath.dirname(path)
        if not path or parent not in origins:  # the root district has no parent
            continue
        origin_x, origin_z = origins[parent]
        slots[parent][posixpath.basename(path)] = (
            entry["layout"]["x"] - origin_x,
            entry["layout"]["z"] - origin_z,
        )
    return dict(slots)


def _pack(
    folder: _Folder,
    path: str,
    sides: dict[str, float],
    previous: PreviousSlots,
    districts: dict[str, Rect],
    buildings: dict[str, Rect],
) -> tuple[float, float, Placer]:
    items: list[Item] = []
    for name, child in folder.folders.items():
        child_path = f"{path}/{name}" if path else name
        width, depth, place = _pack(child, child_path, sides, previous, districts, buildings)
        items.append((name, width, depth, place))
    for name, file_path in folder.files.items():
        side = sides[file_path]
        items.append((name, side, side, _building_placer(file_path, side, buildings)))
    items.sort(key=lambda item: item[0])

    slots = previous.get(path, {})
    if any(name in slots for name, *_ in items):
        content_width, content_depth, offsets = _place_stable(items, slots)
    else:
        content_width, content_depth, offsets = _place_rows(_square_rows(items))
    width = content_width + 2 * MARGIN
    depth = content_depth + 2 * MARGIN

    def place(origin_x: float, origin_z: float) -> None:
        districts[path] = Rect(origin_x, origin_z, width, depth)
        for dx, dz, place_child in offsets:
            place_child(origin_x + MARGIN + dx, origin_z + MARGIN + dz)

    return width, depth, place


def _square_rows(items: list[Item]) -> Rows:
    # Try every row width that fits the first k items exactly and keep the most square result
    # (ties: smaller area), so a few large children do not stack into a long strip.
    candidates = sorted(
        {sum(w + STREET for _, w, _, _ in items[:k]) - STREET for k in range(1, len(items) + 1)}
    )

    def score(rows: Rows) -> tuple[float, float]:
        width, depth, _ = _place_rows(rows)
        return _aspect(width, depth), width * depth

    return min((_shelf_rows(items, target) for target in candidates or [0.0]), key=score)


def _place_stable(
    items: list[Item], slots: dict[str, tuple[float, float]]
) -> tuple[float, float, Offsets]:
    """Keeps previous positions; growth pushes right/down, removals leave gaps."""
    kept = sorted(
        ((slots[item[0]][1], slots[item[0]][0], item) for item in items if item[0] in slots),
        key=lambda entry: (entry[0], entry[1], entry[2][0]),
    )
    rows: list[list[tuple[float, Item]]] = []  # previous x and item, grouped by previous z
    row_zs: list[float] = []
    for z, x, item in kept:
        if not row_zs or z - row_zs[-1] > _ROW_TOLERANCE:
            rows.append([])
            row_zs.append(z)
        rows[-1].append((x, item))

    offsets: Offsets = []
    content_width = 0.0
    row_z = row_bottom = row_end = 0.0
    for previous_z, row in zip(row_zs, rows, strict=True):
        row_z = max(previous_z, row_bottom + STREET) if offsets else max(previous_z, 0.0)
        row_end = -STREET
        row_depth = 0.0
        for previous_x, (_, width, depth, place) in row:
            x = max(previous_x, row_end + STREET)
            offsets.append((x, row_z, place))
            row_end = x + width
            row_depth = max(row_depth, depth)
        content_width = max(content_width, row_end)
        row_bottom = row_z + row_depth

    # New children continue the last row up to the current width, then open rows below.
    new_items = [item for item in items if item[0] not in slots]
    limit = max([content_width, *(width for _, width, _, _ in new_items)])
    for _, width, depth, place in new_items:
        if row_end + STREET + width > limit + 1e-9:
            row_z, row_end = row_bottom + STREET, -STREET
        x = row_end + STREET
        offsets.append((x, row_z, place))
        row_end = x + width
        row_bottom = max(row_bottom, row_z + depth)
        content_width = max(content_width, row_end)
    return content_width, row_bottom, offsets


def _shelf_rows(items: list[Item], row_width: float) -> Rows:
    """Left-to-right rows, starting a new row when the next item would pass row_width."""
    rows: Rows = []
    x = 0.0
    for item in items:
        if not rows or (x > 0 and x + item[1] > row_width + 1e-9):
            rows.append([])
            x = 0.0
        rows[-1].append(item)
        x += item[1] + STREET
    return rows


def _place_rows(rows: Rows) -> tuple[float, float, Offsets]:
    """Offsets of every item when rows are stacked top to bottom; returns content size too."""
    offsets: Offsets = []
    z = content_width = 0.0
    for row in rows:
        x = 0.0
        for _, width, _, place in row:
            offsets.append((x, z, place))
            x += width + STREET
        content_width = max(content_width, x - STREET)
        z += max(depth for _, _, depth, _ in row) + STREET
    return content_width, max(z - STREET, 0.0), offsets


def _aspect(width: float, depth: float) -> float:
    return max(width, depth) / min(width, depth) if min(width, depth) > 0 else math.inf


def _building_placer(path: str, side: float, buildings: dict[str, Rect]) -> Placer:
    def place(x: float, z: float) -> None:
        buildings[path] = Rect(x, z, side, side)

    return place
