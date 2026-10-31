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
        findings.append(
            {
                "id": finding_id,
                "ruleId": rule_id,
                "title": _title(rule),
                "category": _category(tool, rule_id, rule, item, severity_score),
                "severity": _severity(item, rule, severity_score),
                "message": _message(item),
                "location": location,
                "source": {"tool": tool, "version": _text(version), "kind": "scanner"},
                "status": "suppressed" if _suppressed(item) else "open",
            }
        )
    source = {
        "tool": tool,
        "version": _text(version),
        "kind": "scanner",
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


def _severity(item: dict[str, Any], rule: dict[str, Any], score: float | None) -> str:
    if score is not None:
        if score >= 9:
            return "critical"
        if score >= 7:
            return "high"
        if score >= 4:
            return "medium"
        return "low" if score > 0 else "info"
    level = item.get("level") or (rule.get("defaultConfiguration") or {}).get("level") or "warning"
    return _LEVEL_SEVERITY.get(level, "medium")


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
    if lowered.startswith(("cve-", "ghsa-")):
        return "dependencies"
    if lowered.startswith("security/"):  # eslint-plugin-security
        return "security"
    return _TOOL_CATEGORIES.get(tool.lower(), "other")


def _fingerprint(item: dict[str, Any], tool: str, rule_id: str, path: str) -> str:
    """Never derived from line numbers, so a finding survives code moving inside its file."""
    prints = {**(item.get("partialFingerprints") or {}), **(item.get("fingerprints") or {})}
    if prints:
        key, value = sorted(prints.items())[0]
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
            return None
    path = posixpath.normpath(raw.replace("\\", "/"))
    if path.startswith("../") or path in (".", ".."):
        return None
    return path


def _is_absolute_uri(uri: str) -> bool:
    return uri.startswith(("/", "file:")) or bool(re.match(r"^[A-Za-z]:[\\/]", uri))
