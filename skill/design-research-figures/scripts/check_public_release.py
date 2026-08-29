#!/usr/bin/env python3
"""Fail a public release when repository artifacts expose private runtime data."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from public_safety import portable_path


MAX_TEXT_BYTES = 16 * 1024 * 1024
TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".lock",
    ".log",
    ".md",
    ".ndjson",
    ".py",
    ".rst",
    ".sh",
    ".srt",
    ".svg",
    ".tex",
    ".toml",
    ".ts",
    ".tsv",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "dockerfile",
    "license",
}


SENSITIVE_PATTERNS = (
    (
        "api-key",
        re.compile(r"\b" + "sk-" + r"(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    ),
    (
        "authorization-header",
        re.compile(
            r"(?:Author" + r"ization)\s*:"
            r"(?![ \t]*<redacted>)[ \t]*[^\r\n]+",
            re.IGNORECASE,
        ),
    ),
    (
        "bearer-token",
        re.compile(
            r"\b(?:Bear" + r"er)\s+(?!<redacted)[A-Za-z0-9._~+/-]{8,}=*",
            re.IGNORECASE,
        ),
    ),
    (
        "custom-endpoint-setting",
        re.compile(
            r"(?:OPENAI_" + "BASE_" + r"URL|(?:base" + r"[_-]?url)|(?:api" + r"[_-]?base))",
            re.IGNORECASE,
        ),
    ),
    (
        "raw-api-endpoint",
        re.compile(
            r"(?:chat" + "/" + r"completions|v1" + "/" + r"responses)",
            re.IGNORECASE,
        ),
    ),
    (
        "relay-config",
        re.compile(
            r"(?:(?:relay|proxy)[_-]?(?:url|base|endpoint)|OPENAI_"
            + "PROXY|"
            + "中"
            + "转站)",
            re.IGNORECASE,
        ),
    ),
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "macos-user-path",
        re.compile(re.escape("/" + "Users/")),
    ),
    (
        "linux-user-path",
        re.compile(re.escape("/" + "home/")),
    ),
    (
        "macos-private-path",
        re.compile(re.escape("/" + "private/") + r"(?:tmp|var)/"),
    ),
    (
        "windows-user-path",
        re.compile(r"\b[A-Za-z]:\\" + r"Users\\", re.IGNORECASE),
    ),
    (
        "workspace-path",
        re.compile("Desktop/" + "School", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class Issue:
    rule: str
    file: str
    member: str | None = None


def _is_text_name(name: str) -> bool:
    path = PurePosixPath(name)
    return path.suffix.lower() in TEXT_SUFFIXES or path.name.lower() in TEXT_NAMES


def _decode_text(data: bytes, name: str) -> str | None:
    if len(data) > MAX_TEXT_BYTES:
        return None
    if not _is_text_name(name) and b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        if _is_text_name(name):
            return data.decode("utf-8", errors="replace")
        return None


def scan_text(text: str, file_label: str, *, member: str | None = None) -> list[Issue]:
    issues: list[Issue] = []
    for line in text.splitlines():
        for rule, pattern in SENSITIVE_PATTERNS:
            if pattern.search(line):
                issues.append(Issue(rule=rule, file=file_label, member=member))
    return list(dict.fromkeys(issues))


def _walk_json(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def inspect_manifest(
    text: str,
    file_label: str,
    *,
    member: str | None = None,
) -> list[Issue]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [Issue(rule="invalid-manifest-json", file=file_label, member=member)]
    for key, value in _walk_json(payload):
        if key == "response_id" and value not in (None, ""):
            return [Issue(rule="provider-response-id", file=file_label, member=member)]
    return []


def _unsafe_zip_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return (
        normalized.startswith("/")
        or bool(re.match(r"^[A-Za-z]:/", normalized))
        or ".." in path.parts
    )


def inspect_zip(path: Path, file_label: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return [Issue(rule="invalid-zip", file=file_label)]
    with archive:
        for info in archive.infolist():
            if _unsafe_zip_name(info.filename):
                issues.append(
                    Issue(rule="zip-path-traversal", file=file_label, member=info.filename)
                )
            if info.is_dir() or not _is_text_name(info.filename):
                continue
            if info.file_size > MAX_TEXT_BYTES:
                issues.append(
                    Issue(rule="zip-text-too-large", file=file_label, member=info.filename)
                )
                continue
            try:
                data = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                issues.append(
                    Issue(rule="unreadable-zip-entry", file=file_label, member=info.filename)
                )
                continue
            text = _decode_text(data, info.filename)
            if text is None:
                issues.append(
                    Issue(rule="invalid-text-entry", file=file_label, member=info.filename)
                )
                continue
            issues.extend(scan_text(text, file_label, member=info.filename))
            if PurePosixPath(info.filename).name.lower().endswith("manifest.json"):
                issues.extend(inspect_manifest(text, file_label, member=info.filename))
    return list(dict.fromkeys(issues))


def repository_files(root: Path) -> tuple[list[Path], list[Issue]]:
    command = [
        "git",
        "-C",
        str(root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], [Issue(rule="repository-inventory-failed", file=".")]
    if completed.returncode:
        return [], [Issue(rule="repository-inventory-failed", file=".")]
    paths = []
    for raw in completed.stdout.split(b"\x00"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8", errors="surrogateescape"))
        paths.append(root / relative)
    return paths, []


def artifact_files(paths: Iterable[Path]) -> tuple[list[Path], list[Issue]]:
    files: list[Path] = []
    issues: list[Issue] = []
    for raw in paths:
        path = raw.expanduser().absolute()
        if not path.exists():
            issues.append(Issue(rule="missing-artifact", file=path.name))
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
        else:
            files.append(path)
    return files, issues


def inspect_file(path: Path, root: Path) -> list[Issue]:
    label = portable_path(path, root)
    if path.is_symlink():
        try:
            target = path.readlink().as_posix()
        except OSError:
            return [Issue(rule="unreadable-symlink", file=label)]
        return scan_text(target, label)
    if path.suffix.lower() == ".zip":
        return inspect_zip(path, label)
    try:
        data = path.read_bytes()
    except OSError:
        return [Issue(rule="unreadable-file", file=label)]
    text = _decode_text(data, path.name)
    if text is None:
        return []
    issues = scan_text(text, label)
    if path.name.lower().endswith("manifest.json"):
        issues.extend(inspect_manifest(text, label))
    return list(dict.fromkeys(issues))


def run_check(root: Path, artifacts: Iterable[Path] = ()) -> tuple[list[Issue], int]:
    root = root.expanduser().resolve()
    files, issues = repository_files(root)
    extra_files, extra_issues = artifact_files(artifacts)
    issues.extend(extra_issues)
    unique_files = list(dict.fromkeys(path.absolute() for path in (*files, *extra_files)))
    for path in unique_files:
        issues.extend(inspect_file(path, root))
    return list(dict.fromkeys(issues)), len(unique_files)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Git worktree to inspect (default: current directory)",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=Path,
        help="extra release file or directory, including ignored delivery ZIPs; repeatable",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issues, checked = run_check(args.root, args.artifact)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not issues,
                    "checked_files": checked,
                    "issues": [asdict(issue) for issue in issues],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif issues:
        print(f"FAIL: {len(issues)} public-release issue(s) across {checked} file(s).")
        for issue in issues:
            suffix = f"::{issue.member}" if issue.member else ""
            print(f"- [{issue.rule}] {issue.file}{suffix}")
    else:
        print(f"PASS: {checked} release-candidate file(s) passed public checks.")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
