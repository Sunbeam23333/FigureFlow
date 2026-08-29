#!/usr/bin/env python3
"""Audit paper PDFs and optional LaTeX logs with Poppler command-line tools.

The script has no Python package dependencies.  ``pdfinfo`` is required for PDF
structure checks; ``pdffonts`` is used when present and otherwise reported as a
warning.  Any error-level finding makes the process exit non-zero.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from public_safety import portable_path, sanitize_log_text


PAGE_SIZE_RE = re.compile(
    r"^Page(?:\s+\d+)?\s+size:\s*"
    r"(?P<width>[0-9.]+)\s+x\s+(?P<height>[0-9.]+)\s+pts"
    r"(?:\s+\((?P<label>[^)]+)\))?",
    re.MULTILINE,
)
FONT_RE = re.compile(
    r"^(?P<name>.+?)\s{2,}(?P<type>.+?)\s{2,}(?P<encoding>\S+)\s+"
    r"(?P<embedded>yes|no)\s+(?P<subset>yes|no)\s+(?P<unicode>yes|no)\s+",
    re.IGNORECASE,
)

LOG_PATTERNS = (
    ("error", "fatal", re.compile(r"fatal error|emergency stop|no pages of output", re.I)),
    ("error", "latex-error", re.compile(r"^!\s+(?:LaTeX|Package|pdfTeX|XeTeX).*Error", re.I)),
    ("error", "undefined-control-sequence", re.compile(r"undefined control sequence", re.I)),
    ("error", "undefined-reference", re.compile(r"(?:reference|citation).+undefined|undefined references", re.I)),
    ("error", "overfull-box", re.compile(r"overfull \\[hv]box", re.I)),
)


def run_tool(command: list[str]) -> tuple[int, str, str]:
    """Run a bounded command and return its status and decoded output."""
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return 124, stdout, stderr or "command timed out after 30 seconds"
    return completed.returncode, completed.stdout, completed.stderr


def finding(severity: str, code: str, message: str, **details: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if details:
        item["details"] = details
    return item


def parse_page_sizes(text: str) -> list[dict[str, Any]]:
    sizes = []
    for index, match in enumerate(PAGE_SIZE_RE.finditer(text), start=1):
        sizes.append(
            {
                "page": index,
                "width_pt": float(match.group("width")),
                "height_pt": float(match.group("height")),
                "label": match.group("label"),
            }
        )
    return sizes


def audit_pdf(
    path: Path,
    pdfinfo: str | None,
    pdffonts: str | None,
    expected_pages: int | None,
    minimum_pages: int | None,
    *,
    display_path: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "pdf",
        "file": display_path or path.name,
        "pages": None,
        "page_sizes": [],
        "fonts": [],
        "findings": [],
    }
    findings: list[dict[str, Any]] = result["findings"]

    if not path.is_file():
        findings.append(finding("error", "missing-file", "PDF does not exist."))
        return result
    if path.suffix.lower() != ".pdf":
        findings.append(finding("error", "not-pdf", "Input does not have a .pdf suffix."))
        return result
    if not pdfinfo:
        findings.append(finding("error", "missing-pdfinfo", "pdfinfo is not available on PATH."))
        return result

    returncode, stdout, stderr = run_tool([pdfinfo, str(path)])
    if returncode != 0:
        findings.append(
            finding(
                "error",
                "pdfinfo-failed",
                "pdfinfo could not inspect the PDF.",
                returncode=returncode,
                stderr=sanitize_log_text(stderr, local_roots=(path.parent,)).strip(),
            )
        )
        return result

    page_match = re.search(r"^Pages:\s*(\d+)\s*$", stdout, re.MULTILINE)
    if not page_match:
        findings.append(finding("error", "missing-page-count", "pdfinfo returned no page count."))
        return result

    pages = int(page_match.group(1))
    result["pages"] = pages
    if pages < 1:
        findings.append(finding("error", "empty-pdf", "PDF has no pages."))
        return result
    if expected_pages is not None and pages != expected_pages:
        findings.append(
            finding(
                "error",
                "unexpected-page-count",
                f"Expected {expected_pages} page(s), found {pages}.",
                expected=expected_pages,
                actual=pages,
            )
        )
    if minimum_pages is not None and pages < minimum_pages:
        findings.append(
            finding(
                "error",
                "too-few-pages",
                f"Expected at least {minimum_pages} page(s), found {pages}.",
                minimum=minimum_pages,
                actual=pages,
            )
        )

    size_code, size_stdout, size_stderr = run_tool(
        [pdfinfo, "-f", "1", "-l", str(pages), str(path)]
    )
    if size_code != 0:
        findings.append(
            finding(
                "error",
                "page-size-check-failed",
                "pdfinfo could not read per-page dimensions.",
                returncode=size_code,
                stderr=sanitize_log_text(size_stderr, local_roots=(path.parent,)).strip(),
            )
        )
    else:
        sizes = parse_page_sizes(size_stdout)
        result["page_sizes"] = sizes
        if len(sizes) != pages:
            findings.append(
                finding(
                    "error",
                    "missing-page-size",
                    f"Read dimensions for {len(sizes)} of {pages} page(s).",
                )
            )
        if any(size["width_pt"] <= 0 or size["height_pt"] <= 0 for size in sizes):
            findings.append(finding("error", "invalid-page-size", "A page has non-positive dimensions."))
        distinct_sizes = {
            (round(size["width_pt"], 2), round(size["height_pt"], 2)) for size in sizes
        }
        if len(distinct_sizes) > 1:
            findings.append(
                finding(
                    "warning",
                    "mixed-page-sizes",
                    f"PDF contains {len(distinct_sizes)} distinct page dimensions.",
                    sizes_pt=sorted(distinct_sizes),
                )
            )

    if not pdffonts:
        findings.append(
            finding("warning", "missing-pdffonts", "pdffonts is unavailable; font checks were skipped.")
        )
    else:
        font_code, font_stdout, font_stderr = run_tool([pdffonts, str(path)])
        if font_code != 0:
            findings.append(
                finding(
                    "error",
                    "pdffonts-failed",
                    "pdffonts could not inspect the PDF.",
                    returncode=font_code,
                    stderr=sanitize_log_text(font_stderr, local_roots=(path.parent,)).strip(),
                )
            )
        else:
            fonts = []
            for line in font_stdout.splitlines()[2:]:
                match = FONT_RE.match(line)
                if not match:
                    continue
                fonts.append(
                    {
                        "name": match.group("name").strip(),
                        "type": match.group("type").strip(),
                        "encoding": match.group("encoding"),
                        "embedded": match.group("embedded").lower() == "yes",
                        "subset": match.group("subset").lower() == "yes",
                        "unicode": match.group("unicode").lower() == "yes",
                    }
                )
            result["fonts"] = fonts
            unembedded = [font["name"] for font in fonts if not font["embedded"]]
            type_three = [font["name"] for font in fonts if font["type"].lower().startswith("type 3")]
            if unembedded:
                findings.append(
                    finding(
                        "error",
                        "unembedded-font",
                        f"Found {len(unembedded)} unembedded font(s).",
                        fonts=unembedded,
                    )
                )
            if type_three:
                findings.append(
                    finding(
                        "error",
                        "type-3-font",
                        f"Found {len(type_three)} Type 3 font(s).",
                        fonts=type_three,
                    )
                )

    return result


def audit_log(path: Path, *, display_path: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "latex-log",
        "file": display_path or path.name,
        "findings": [],
    }
    findings: list[dict[str, Any]] = result["findings"]
    if not path.is_file():
        findings.append(finding("error", "missing-file", "LaTeX log does not exist."))
        return result
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        findings.append(finding("error", "unreadable-log", "Could not read log."))
        return result

    seen: set[tuple[str, str]] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        line = sanitize_log_text(raw_line, local_roots=(path.parent,)).strip()
        for severity, code, pattern in LOG_PATTERNS:
            if not pattern.search(line):
                continue
            key = (code, line)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                finding(
                    severity,
                    code,
                    line[:300],
                    line=line_number,
                )
            )
    return result


def result_status(result: dict[str, Any]) -> str:
    severities = {item["severity"] for item in result["findings"]}
    if "error" in severities:
        return "FAIL"
    if "warning" in severities:
        return "WARN"
    return "PASS"


def human_report(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for result in results:
        status = result_status(result)
        lines.append(f"{status:4} {result['file']}")
        if result["kind"] == "pdf" and result.get("pages") is not None:
            sizes = result.get("page_sizes", [])
            distinct = []
            for size in sizes:
                label = f" ({size['label']})" if size.get("label") else ""
                description = f"{size['width_pt']:g} x {size['height_pt']:g} pt{label}"
                if description not in distinct:
                    distinct.append(description)
            dimensions = ", ".join(distinct) if distinct else "unknown"
            lines.append(
                f"     pages={result['pages']} sizes={dimensions} fonts={len(result.get('fonts', []))}"
            )
        if not result["findings"]:
            lines.append("     no issues found")
        for item in result["findings"]:
            location = ""
            if item.get("details", {}).get("line"):
                location = f" line {item['details']['line']}"
            lines.append(
                f"     {item['severity'].upper():7} [{item['code']}]{location}: {item['message']}"
            )

    errors = sum(
        item["severity"] == "error" for result in results for item in result["findings"]
    )
    warnings = sum(
        item["severity"] == "warning" for result in results for item in result["findings"]
    )
    lines.append(f"Summary: {len(results)} artifact(s), {errors} error(s), {warnings} warning(s).")
    return "\n".join(lines)


def build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    errors = sum(
        item["severity"] == "error" for result in results for item in result["findings"]
    )
    warnings = sum(
        item["severity"] == "warning" for result in results for item in result["findings"]
    )
    return {
        "ok": errors == 0,
        "summary": {"artifacts": len(results), "errors": errors, "warnings": warnings},
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", type=Path, help="one or more PDF files")
    page_group = parser.add_mutually_exclusive_group()
    page_group.add_argument(
        "--single-page",
        action="store_true",
        help="require every input PDF to contain exactly one page",
    )
    page_group.add_argument(
        "--expect-pages",
        type=int,
        metavar="N",
        help="require every input PDF to contain exactly N pages",
    )
    parser.add_argument(
        "--min-pages",
        type=int,
        metavar="N",
        help="require every input PDF to contain at least N pages",
    )
    parser.add_argument(
        "--log",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help="scan a LaTeX compile log; repeat for multiple logs",
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument(
        "--json-output",
        type=Path,
        metavar="PATH",
        help="also write the complete report to a JSON file",
    )
    args = parser.parse_args()
    if args.expect_pages is not None and args.expect_pages < 1:
        parser.error("--expect-pages must be at least 1")
    if args.min_pages is not None and args.min_pages < 1:
        parser.error("--min-pages must be at least 1")
    return args


def main() -> int:
    args = parse_args()
    expected_pages = 1 if args.single_page else args.expect_pages
    pdfinfo = shutil.which("pdfinfo")
    pdffonts = shutil.which("pdffonts")
    report_base = (
        args.json_output.expanduser().resolve().parent
        if args.json_output
        else Path.cwd().resolve()
    )
    pdf_paths = [path.expanduser().resolve() for path in args.pdfs]
    log_paths = [path.expanduser().resolve() for path in args.log]
    results = [
        audit_pdf(
            path,
            pdfinfo,
            pdffonts,
            expected_pages,
            args.min_pages,
            display_path=portable_path(path, report_base),
        )
        for path in pdf_paths
    ]
    results.extend(
        audit_log(path, display_path=portable_path(path, report_base))
        for path in log_paths
    )
    report = build_report(results)

    if args.json_output:
        json_path = args.json_output.expanduser().resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(human_report(results))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
