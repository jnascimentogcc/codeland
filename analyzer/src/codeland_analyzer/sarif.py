"""SARIF 2.1.0 importer: scanner results -> findings of the city model (docs section 6)."""

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

MESSAGE_MAX = 300
_LEVEL_SEVERITY = {"error": "high", "warning": "medium", "note": "low", "none": "info"}
_TAG_CATEGORIES = (  # first match wins, so security outranks the rest
    ("security", "security"),
    ("cwe-", "security"),
    ("vulnerability", "security"),
    ("dependenc", "dependencies"),
    ("reliab", "reliability"),
    ("correctness", "reliability"),
    ("bug", "reliability"),
    ("performance", "performance"),
    ("maintainab", "maintainability"),
    ("complexity", "maintainability"),
    ("style", "maintainability"),
    ("test", "testing"),
)
_TOOL_CATEGORIES = {"gitleaks": "security", "trufflehog": "security", "eslint": "maintainability"}
CATEGORY_IDS = {c for _, c in _TAG_CATEGORIES} | {"other"}
KIND_PROPERTY = "codeland/kind"  # tool.driver.properties; "agent" marks a sweep agent (docs 6.8)
FINGERPRINT_KEY = "codeland/finding/v1"  # result.fingerprints: the id an agent chooses itself
_WHITESPACE = re.compile(r"\s+")
_WINDOWS_DRIVE = re.compile(r"^/[A-Za-z]:")


class SarifError(ValueError):
    pass


@dataclass
class SarifImport:
    findings: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)


def read_sarif(path: Path, repo: Path) -> SarifImport:
    """Findings of every run in a SARIF file; paths are made relative to `repo`."""
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise SarifError(f"{path}: cannot read SARIF ({error})") from error
    if not isinstance(document, dict) or document.get("version") != "2.1.0":
        version = document.get("version") if isinstance(document, dict) else None
        raise SarifError(f"{path}: only SARIF 2.1.0 is supported (found version {version!r})")

    result = SarifImport()
    seen: set[str] = set()
    for run in document.get("runs") or []:
        findings, source = _read_run(run, repo.resolve(), path, seen)
        result.findings.extend(findings)
        result.sources.append(source)
    return result


def _read_run(
    run: dict[str, Any], repo: Path, file: Path, seen: set[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    driver = (run.get("tool") or {}).get("driver") or {}
    tool = str(driver.get("name") or "unknown")
    version = driver.get("semanticVersion") or driver.get("version")
    kind = "agent" if (driver.get("properties") or {}).get(KIND_PROPERTY) == "agent" else "scanner"
    rules = _collect_rules(run)
    bases = {
        name: (value or {}).get("uri")
        for name, value in (run.get("originalUriBaseIds") or {}).items()
    }

    findings: list[dict[str, Any]] = []
    dropped = 0
    occurrences: dict[str, int] = {}
    for item in run.get("results") or []:
        rule_id = _rule_id(item, rules)
        rule = rules.get(rule_id, {})
        location = _location(item, repo, bases)
        if rule_id is None or location is None:
            dropped += 1
            continue
        base_id = _fingerprint(item, tool, rule_id, location["path"])
        occurrences[base_id] = occurrences.get(base_id, 0) + 1
        finding_id = base_id if occurrences[base_id] == 1 else f"{base_id}-{occurrences[base_id]}"
        if finding_id in seen:
            dropped += 1
            continue
        seen.add(finding_id)
        severity_score = _security_severity(item, rule)
        category = _category(tool, rule_id, rule, item, severity_score)
        findings.append(
            {
                "id": finding_id,
                "ruleId": rule_id,
                "title": _title(rule),
                "category": category,
                "severity": _severity(item, rule, severity_score, category),
                "message": _message(item),
                "location": location,
                "source": {"tool": tool, "version": _text(version), "kind": kind},
                "status": "suppressed" if _suppressed(item) else "open",
            }
        )
    source = {
        "tool": tool,
        "version": _text(version),
        "kind": kind,
        "file": file.name,
        "findings": len(findings),
        "dropped": dropped,
    }
    return findings, source


def _collect_rules(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tool = run.get("tool") or {}
    rules: dict[str, dict[str, Any]] = {}
    for component in [tool.get("driver") or {}, *(tool.get("extensions") or [])]:
        for rule in component.get("rules") or []:
            if isinstance(rule, dict) and rule.get("id"):
                rules.setdefault(rule["id"], rule)
    return rules


def _rule_id(item: dict[str, Any], rules: dict[str, dict[str, Any]]) -> str | None:
    rule_id = item.get("ruleId") or (item.get("rule") or {}).get("id")
    if rule_id:
        return str(rule_id)
    index = item.get("ruleIndex")
    if isinstance(index, int) and 0 <= index < len(rules):
        return list(rules)[index]
    return None


def _title(rule: dict[str, Any]) -> str | None:
    short = (rule.get("shortDescription") or {}).get("text")
    return _text(short or rule.get("name"))


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _message(item: dict[str, Any]) -> str:
    message = item.get("message") or {}
    text = message.get("text") or message.get("markdown") or ""
    text = _WHITESPACE.sub(" ", str(text)).strip()
    return text if len(text) <= MESSAGE_MAX else text[: MESSAGE_MAX - 1] + "…"


def _suppressed(item: dict[str, Any]) -> bool:
    suppressions = item.get("suppressions") or []
    return any(s.get("status") != "rejected" for s in suppressions if isinstance(s, dict))


def _security_severity(item: dict[str, Any], rule: dict[str, Any]) -> float | None:
    for properties in (item.get("properties"), rule.get("properties")):
        value = (properties or {}).get("security-severity")
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _severity(
    item: dict[str, Any], rule: dict[str, Any], score: float | None, category: str
) -> str:
    if score is not None:
        if score >= 9:
            return "critical"
        if score >= 7:
            return "high"
        if score >= 4:
            return "medium"
        return "low" if score > 0 else "info"
    level = item.get("level") or (rule.get("defaultConfiguration") or {}).get("level") or "warning"
    severity = _LEVEL_SEVERITY.get(level, "medium")
    # Linters report their must-fix style rules as "error"; that is not an urgent problem.
    return "medium" if severity == "high" and category == "maintainability" else severity


def _category(
    tool: str, rule_id: str, rule: dict[str, Any], item: dict[str, Any], score: float | None
) -> str:
    if score is not None:
        return "security"
    tags = [
        str(tag).lower()
        for properties in (item.get("properties"), rule.get("properties"))
        for tag in (properties or {}).get("tags") or []
    ]
    for needle, category in _TAG_CATEGORIES:
        if any(needle in tag for tag in tags):
            return category
    lowered = rule_id.lower()
    parts = lowered.split("/")
    if parts[0] == "agent" and len(parts) > 2 and parts[1] in CATEGORY_IDS:  # agent/<category>/x
        return parts[1]
    if lowered.startswith(("cve-", "ghsa-")):
        return "dependencies"
    if lowered.startswith("security/"):  # eslint-plugin-security
        return "security"
    return _TOOL_CATEGORIES.get(tool.lower(), "other")


def _fingerprint(item: dict[str, Any], tool: str, rule_id: str, path: str) -> str:
    """Never derived from line numbers, so a finding survives code moving inside its file."""
    prints = {**(item.get("partialFingerprints") or {}), **(item.get("fingerprints") or {})}
    # Semgrep OSS fills the placeholder "requires login", identical for every result.
    prints = {k: v for k, v in prints.items() if isinstance(v, str) and v and " " not in v}
    if prints:
        key, value = min(prints.items(), key=lambda kv: (kv[0] != FINGERPRINT_KEY, kv[0]))
        basis = f"{key}={value}"
    else:
        region = ((item.get("locations") or [{}])[0].get("physicalLocation") or {}).get("region")
        snippet = ((region or {}).get("snippet") or {}).get("text")
        basis = _WHITESPACE.sub(" ", snippet or _message(item)).strip()
    digest = hashlib.sha256("\x1f".join((tool, rule_id, path, basis)).encode()).hexdigest()
    return digest[:16]


def _location(
    item: dict[str, Any], repo: Path, bases: dict[str, str | None]
) -> dict[str, Any] | None:
    for location in item.get("locations") or []:
        physical = (location or {}).get("physicalLocation") or {}
        artifact = physical.get("artifactLocation") or {}
        path = _repo_path(artifact.get("uri"), artifact.get("uriBaseId"), repo, bases)
        if path is None:
            continue
        region = physical.get("region") or {}
        start = _line(region.get("startLine"))
        end = _line(region.get("endLine")) or start
        return {"path": path, "startLine": start, "endLine": end}
    return None


def _line(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 1 else None


def _repo_path(
    uri: object, base_id: object, repo: Path, bases: dict[str, str | None]
) -> str | None:
    if not isinstance(uri, str) or not uri:
        return None
    if isinstance(base_id, str) and (base := bases.get(base_id)):
        uri = base.rstrip("/") + "/" + uri.lstrip("/") if not _is_absolute_uri(uri) else uri
    parsed = urlparse(uri)
    raw = unquote(parsed.path if parsed.scheme == "file" else uri)
    if parsed.scheme == "file" or _is_absolute_uri(raw):
        if _WINDOWS_DRIVE.match(raw):
            raw = raw[1:]
        try:
            return Path(raw).resolve().relative_to(repo).as_posix()
        except ValueError:
            return _suffix_in_repo(raw, repo)
    path = posixpath.normpath(raw.replace("\\", "/"))
    if path.startswith("../") or path in (".", ".."):
        return None
    return path


def _suffix_in_repo(raw: str, repo: Path) -> str | None:
    """Containers and CI report paths like /src/src/a.ts or /home/runner/work/r/r/src/a.ts: take
    the longest tail that is a file of the repo (a lone file name only right under a root)."""
    parts = [p for p in re.split(r"[\/]+", raw) if p and p != "."]
    if ".." in parts:
        return None
    for start in range(len(parts)):
        tail = parts[start:]
        if len(tail) == 1 and len(parts) > 2:
            break
        if (repo.joinpath(*tail)).is_file():
            return "/".join(tail)
    return None


def _is_absolute_uri(uri: str) -> bool:
    return uri.startswith(("/", "file:")) or bool(re.match(r"^[A-Za-z]:[\\/]", uri))
