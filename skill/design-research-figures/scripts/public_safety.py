#!/usr/bin/env python3
"""Portable path labels and redaction helpers for public artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


_REDACTIONS = (
    (
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
        "<redacted-api-key>",
    ),
    (
        re.compile(r"\b(?:Bear" + r"er)\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
        "Bearer <redacted-token>",
    ),
    (
        re.compile(r"(?:Author" + r"ization)\s*:\s*[^\r\n]+", re.IGNORECASE),
        "Authorization: <redacted>",
    ),
    (
        re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE),
        "<redacted-url>",
    ),
    (
        re.compile(r"(?<![A-Za-z0-9])/(?:Users|home)/[^\s<>\"']+"),
        "<local-path>",
    ),
    (
        re.compile(
            r"(?<![A-Za-z0-9])/" + r"private/(?:tmp|var)/[^\s<>\"']+"
        ),
        "<local-path>",
    ),
    (
        re.compile(r"\b[A-Za-z]:\\Users\\[^\s<>\"']+", re.IGNORECASE),
        "<local-path>",
    ),
    (
        re.compile(
            r"(?<![A-Za-z0-9:])/" + r"(?=[A-Za-z0-9._-])[^\s<>\"']+"
        ),
        "<local-path>",
    ),
)


def portable_path(path: Path, base: Path) -> str:
    """Return a relative public label, falling back to the basename."""
    resolved_path = path.expanduser().resolve()
    resolved_base = base.expanduser().resolve()
    try:
        return resolved_path.relative_to(resolved_base).as_posix()
    except ValueError:
        return resolved_path.name


def sanitize_log_text(text: str, *, local_roots: Iterable[Path] = ()) -> str:
    """Remove credentials, URLs, and machine-specific paths from log text."""
    sanitized = text
    roots = sorted(
        {str(path.expanduser().resolve()) for path in local_roots},
        key=len,
        reverse=True,
    )
    for root in roots:
        if root and root != "/":
            sanitized = sanitized.replace(root, "<local-root>")
    for pattern, replacement in _REDACTIONS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_log_file(path: Path, *, local_roots: Iterable[Path] = ()) -> None:
    """Sanitize an existing UTF-8-ish log in place when it exists."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(
        sanitize_log_text(text, local_roots=local_roots),
        encoding="utf-8",
    )
