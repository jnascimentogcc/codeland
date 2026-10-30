"""Resolution of import specifiers to repository files.

Only relative specifiers are resolved. Bare specifiers are treated as external packages;
tsconfig `paths`/`baseUrl` aliases are not supported yet and also count as external.
"""

import posixpath

_SUFFIX_CANDIDATES = ("", ".ts", ".tsx", ".mts", ".cts", "/index.ts", "/index.tsx")
# ESM TypeScript imports name the emitted file ("./a.js") while the source is "./a.ts".
_JS_TO_TS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}


def is_relative(specifier: str) -> bool:
    return specifier == "." or specifier == ".." or specifier.startswith(("./", "../"))


def resolve(importer: str, specifier: str, known_files: set[str]) -> str | None:
    if not is_relative(specifier):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
    stem, ext = posixpath.splitext(base)
    candidates = [base + suffix for suffix in _SUFFIX_CANDIDATES]
    candidates += [stem + ts_ext for ts_ext in _JS_TO_TS.get(ext, ())]
    return next((c for c in candidates if c in known_files), None)
