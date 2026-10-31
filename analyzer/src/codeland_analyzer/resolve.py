"""Resolution of import specifiers to repository files.

Relative specifiers resolve against the importer. Bare specifiers resolve only through the
nearest tsconfig.json's `paths`/`baseUrl` (following relative `extends`) and only when they land
on a repository file; everything else is an external package.
"""

import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

_SUFFIX_CANDIDATES = ("", ".ts", ".tsx", ".mts", ".cts", "/index.ts", "/index.tsx")
# ESM TypeScript imports name the emitted file ("./a.js") while the source is "./a.ts".
_JS_TO_TS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
_MAX_EXTENDS = 8


def is_relative(specifier: str) -> bool:
    return specifier == "." or specifier == ".." or specifier.startswith(("./", "../"))


def _candidates(base: str) -> list[str]:
    stem, ext = posixpath.splitext(base)
    return [base + suffix for suffix in _SUFFIX_CANDIDATES] + [
        stem + ts_ext for ts_ext in _JS_TO_TS.get(ext, ())
    ]


def _first_known(base: str, known_files: set[str]) -> str | None:
    return next((c for c in _candidates(base) if c in known_files), None)


@dataclass
class TsConfig:
    """The path mapping of one tsconfig.json, in repository-relative terms."""

    folder: str
    # Where `paths` targets (and bare baseUrl lookups) are anchored.
    base: str
    has_base_url: bool = False
    # (pattern, targets): "@app/*" -> ["src/app/*"] with targets already anchored to `base`.
    paths: list[tuple[str, list[str]]] = field(default_factory=list)

    def resolve(self, specifier: str, known_files: set[str]) -> str | None:
        best: tuple[int, list[str], str] | None = None
        for pattern, targets in self.paths:
            star = pattern.find("*")
            if star < 0:
                matched = specifier == pattern
                rest = ""
                weight = len(pattern)
            else:
                prefix, suffix = pattern[:star], pattern[star + 1 :]
                matched = (
                    len(specifier) >= len(prefix) + len(suffix)
                    and specifier.startswith(prefix)
                    and specifier.endswith(suffix)
                )
                rest = specifier[len(prefix) : len(specifier) - len(suffix)]
                weight = len(prefix)
            # TypeScript picks the pattern with the longest prefix.
            if matched and (best is None or weight > best[0]):
                best = (weight, targets, rest)
        if best is not None:
            for target in best[1]:
                hit = _first_known(posixpath.normpath(target.replace("*", best[2])), known_files)
                if hit:
                    return hit
        if self.has_base_url:
            return _first_known(
                posixpath.normpath(posixpath.join(self.base, specifier)), known_files
            )
        return None


def parse_jsonc(text: str) -> object:
    """JSON with comments and trailing commas, as tsconfig files are written."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(ch)
            i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


def _read_options(repo: Path, config: str, depth: int = 0) -> tuple[dict, dict[str, str]] | None:
    """compilerOptions of a tsconfig merged over its `extends` chain, plus the folder that its
    own `baseUrl`/`paths` are relative to (the config that defines them)."""
    try:
        data = parse_jsonc((repo / config).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    options = data.get("compilerOptions")
    options = dict(options) if isinstance(options, dict) else {}
    folder = posixpath.dirname(config)
    # Each option is anchored to the folder of the config that set it; remember that.
    origin = {key: folder for key in ("baseUrl", "paths")}
    parent = data.get("extends")
    if isinstance(parent, str) and parent.startswith(".") and depth < _MAX_EXTENDS:
        target = posixpath.normpath(posixpath.join(folder, parent))
        if not target.endswith(".json"):
            target += ".json"
        inherited = _read_options(repo, target, depth + 1)
        if inherited:
            base_options, base_origin = inherited
            for key in ("baseUrl", "paths"):
                if key not in options and key in base_options:
                    options[key] = base_options[key]
                    origin[key] = base_origin[key]
    return options, origin


def load_tsconfigs(repo: Path, config_files: list[str]) -> list[TsConfig]:
    """One path mapping per tsconfig.json that declares `paths` or `baseUrl`."""
    configs: list[TsConfig] = []
    for config in config_files:
        read = _read_options(repo, config)
        if read is None:
            continue
        options, origin = read
        folder = posixpath.dirname(config)
        base_url = options.get("baseUrl")
        raw_paths = options.get("paths")
        if not isinstance(base_url, str) and not isinstance(raw_paths, dict):
            continue
        if isinstance(base_url, str):
            base = posixpath.normpath(posixpath.join(origin["baseUrl"], base_url))
        else:
            # Without baseUrl, `paths` are relative to the config that declares them.
            base = origin["paths"]
        paths: list[tuple[str, list[str]]] = []
        if isinstance(raw_paths, dict):
            anchor = base if isinstance(base_url, str) else origin["paths"]
            for pattern, targets in raw_paths.items():
                if isinstance(targets, list):
                    anchored = [
                        posixpath.normpath(posixpath.join(anchor, t))
                        for t in targets
                        if isinstance(t, str)
                    ]
                    paths.append((pattern, anchored))
        configs.append(TsConfig(folder or ".", base or ".", isinstance(base_url, str), paths))
    return configs


def nearest(importer: str, configs: list[TsConfig]) -> TsConfig | None:
    """The tsconfig of the deepest folder that contains the importer."""
    folder = posixpath.dirname(importer) or "."
    best: TsConfig | None = None
    for config in configs:
        inside = (
            config.folder == "."
            or folder == config.folder
            or folder.startswith(config.folder + "/")
        )
        if inside and (best is None or len(config.folder) > len(best.folder)):
            best = config
    return best


def resolve(
    importer: str,
    specifier: str,
    known_files: set[str],
    tsconfigs: list[TsConfig] | None = None,
) -> str | None:
    if is_relative(specifier):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
        return _first_known(base, known_files)
    config = nearest(importer, tsconfigs) if tsconfigs else None
    return config.resolve(specifier, known_files) if config else None
