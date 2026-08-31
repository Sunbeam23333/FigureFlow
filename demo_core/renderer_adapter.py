"""Bounded adapter around the deterministic renderer and QA scripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / "skill" / "design-research-figures" / "scripts"
RENDERER = SKILL_SCRIPTS / "render_workflow.py"
PNG_AUDITOR = SKILL_SCRIPTS / "audit_figure.py"
PDF_AUDITOR = SKILL_SCRIPTS / "qa_pdf.py"


class RenderError(RuntimeError):
    """A deterministic render or QA failure."""


def _portable(value: object, base: Path) -> object:
    """Remove machine-specific absolute paths from reports before persistence."""
    if isinstance(value, dict):
        return {key: _portable(item, base) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable(item, base) for item in value]
    if isinstance(value, str) and os.path.isabs(value):
        path = Path(value).resolve()
        try:
            return path.relative_to(base.resolve()).as_posix()
        except ValueError:
            return path.name
    return value


def _run(command: list[str], *, timeout: int = 120, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0 and not allow_failure:
        detail = (completed.stderr or completed.stdout).strip()
        raise RenderError(detail[-1600:] or "renderer failed")
    return completed


def render_plan(plan_path: Path, asset_dir: Path, output_dir: Path, output_name: str) -> dict[str, str]:
    completed = _run(
        [
            sys.executable,
            str(RENDERER),
            str(plan_path),
            "--asset-dir",
            str(asset_dir),
            "--output-dir",
            str(output_dir),
            "--output-name",
            output_name,
        ]
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RenderError("renderer returned an invalid manifest") from exc


def audit_outputs(png_path: Path, pdf_path: Path, report_dir: Path) -> dict[str, object]:
    report_dir.mkdir(parents=True, exist_ok=True)
    png_run = _run(
        [
            sys.executable,
            str(PNG_AUDITOR),
            str(png_path),
            "--margin",
            "16",
            "--background-model",
            "bilinear-corners",
            "--json",
        ],
        allow_failure=True,
    )
    pdf_report_path = report_dir / "pdf_qa.json"
    pdf_run = _run(
        [
            sys.executable,
            str(PDF_AUDITOR),
            str(pdf_path),
            "--single-page",
            "--json",
            "--json-output",
            str(pdf_report_path),
        ],
        allow_failure=True,
    )
    privacy_base = report_dir.parent
    try:
        png_report = _portable(json.loads(png_run.stdout), privacy_base)
    except json.JSONDecodeError:
        png_report = [{"clipping_risk": True, "error": (png_run.stderr or png_run.stdout)[-800:]}]
    try:
        pdf_report = _portable(json.loads(pdf_run.stdout), privacy_base)
    except json.JSONDecodeError:
        pdf_report = {"ok": False, "error": (pdf_run.stderr or pdf_run.stdout)[-800:]}
    font_names = [
        str(font.get("name", ""))
        for result in pdf_report.get("results", [])
        for font in result.get("fonts", [])
    ] if isinstance(pdf_report, dict) else []
    cjk_tokens = ("ArialUnicode", "NotoSansCJK", "SourceHan", "PingFang", "YaHei", "HiraginoSansGB", "Heiti")
    cjk_font_embedded = any(any(token.lower() in name.replace(" ", "").lower() for token in cjk_tokens) for name in font_names)
    report = {
        "ok": png_run.returncode == 0 and pdf_run.returncode == 0 and cjk_font_embedded,
        "cjk_font_embedded": cjk_font_embedded,
        "font_names": font_names,
        "png": png_report,
        "pdf": pdf_report,
    }
    (report_dir / "qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pdf_report_path.write_text(json.dumps(pdf_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
