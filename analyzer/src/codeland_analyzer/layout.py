"""Deterministic city layout: folders become nested districts, files become buildings.

Children of a district are sorted by name and shelf-packed into rows whose width keeps the district
close to square, so the same input always yields the same city. Adding a file can still reflow its
district (and resize the enclosing ones).
Full incremental stability (reusing positions from a previous model, docs/architecture_and_mvp.md
section 2.3) is not implemented yet.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

STREET = 1.0  # gap between items inside a district
MARGIN = 1.0  # border between a district's edge and its content


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


Placer = Callable[[float, float], None]


def footprint_side(imports: int) -> float:
    """Building side length; area grows linearly with efferent coupling."""
    return 1.0 + math.sqrt(imports)


def layout_city(sides: dict[str, float]) -> tuple[dict[str, Rect], dict[str, Rect]]:
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
    _, _, place = _pack(root, "", sides, districts, buildings)
    place(0.0, 0.0)
    return districts, buildings


def _pack(
    folder: _Folder,
    path: str,
    sides: dict[str, float],
    districts: dict[str, Rect],
    buildings: dict[str, Rect],
) -> tuple[float, float, Placer]:
    items: list[tuple[str, float, float, Placer]] = []
    for name, child in folder.folders.items():
        child_path = f"{path}/{name}" if path else name
        width, depth, place = _pack(child, child_path, sides, districts, buildings)
        items.append((name, width, depth, place))
    for name, file_path in folder.files.items():
        side = sides[file_path]
        items.append((name, side, side, _building_placer(file_path, side, buildings)))
    items.sort(key=lambda item: item[0])

    # Try every row width that fits the first k items exactly and keep the most square result
    # (ties: smaller area), so a few large children do not stack into a long strip.
    candidates = sorted(
        {sum(w + STREET for _, w, _, _ in items[:k]) - STREET for k in range(1, len(items) + 1)}
    )
    content_width, content_depth, offsets = min(
        (_shelf(items, target) for target in candidates or [0.0]),
        key=lambda packed: (_aspect(packed[0], packed[1]), packed[0] * packed[1]),
    )

    width = content_width + 2 * MARGIN
    depth = content_depth + 2 * MARGIN

    def place(origin_x: float, origin_z: float) -> None:
        districts[path] = Rect(origin_x, origin_z, width, depth)
        for dx, dz, place_child in offsets:
            place_child(origin_x + MARGIN + dx, origin_z + MARGIN + dz)

    return width, depth, place


def _shelf(
    items: list[tuple[str, float, float, Placer]], row_width: float
) -> tuple[float, float, list[tuple[float, float, Placer]]]:
    """Left-to-right rows, starting a new row when the next item would pass row_width."""
    offsets: list[tuple[float, float, Placer]] = []
    x = z = row_depth = content_width = 0.0
    for _, width, depth, place in items:
        if x > 0 and x + width > row_width + 1e-9:
            z += row_depth + STREET
            x = row_depth = 0.0
        offsets.append((x, z, place))
        content_width = max(content_width, x + width)
        row_depth = max(row_depth, depth)
        x += width + STREET
    return content_width, z + row_depth, offsets


def _aspect(width: float, depth: float) -> float:
    return max(width, depth) / min(width, depth) if min(width, depth) > 0 else math.inf


def _building_placer(path: str, side: float, buildings: dict[str, Rect]) -> Placer:
    def place(x: float, z: float) -> None:
        buildings[path] = Rect(x, z, side, side)

    return place
