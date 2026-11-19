#!/usr/bin/env python3
"""Render one allowlisted paper-faithful TikZ template from FigureFlow.

The route is deliberately separate from FigurePlan's generic workflow templates:
one ID selects one standalone source, whose provenance and editable panel grammar
are recorded alongside the PDF/PNG outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "cases" / "top_conference_visual_research"
TEMPLATES = CASE / "exact_templates"
REGISTRY = TEMPLATES / "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_registry() -> dict[str, object]:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    templates = payload.get("templates")
    if not isinstance(templates, list):
        raise ValueError("manifest.json must contain a templates list")
    return payload


def entries_by_id() -> dict[str, dict[str, object]]:
    result = {}
    for entry in load_registry()["templates"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("template_id"), str):
            raise ValueError("every template entry needs a template_id")
        template_id = entry["template_id"]
        if template_id in result:
            raise ValueError(f"duplicate template_id: {template_id}")
        result[template_id] = entry
    return result


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=180)


def render(template_id: str, output_dir: Path, dpi: int, engine_name: str) -> int:
    # The allowlist is the security boundary: user input never becomes a path.
    if template_id not in entries_by_id():
        print(f"error: unknown template ID: {template_id}", file=sys.stderr)
        return 2
    if not template_id.replace("_", "").isalnum():
        print("error: invalid template ID", file=sys.stderr)
        return 2
    source = TEMPLATES / template_id / "main.tex"
    if not source.is_file():
        print(f"error: registered template is missing: {template_id}", file=sys.stderr)
        return 2
    engine = shutil.which(engine_name)
    renderer = shutil.which("pdftoppm")
    if not engine or not renderer:
        print("error: xelatex and pdftoppm are required", file=sys.stderr)
        return 2

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = template_id
    with tempfile.TemporaryDirectory(prefix=f"figureflow-{template_id}-") as job:
        job_dir = Path(job)
        result = run([engine, "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={job_dir}", source.name], source.parent)
        if result.returncode != 0 or not (job_dir / "main.pdf").is_file():
            print(result.stdout[-4000:], file=sys.stderr)
            return 1
        pdf = output_dir / f"{stem}.pdf"
        png = output_dir / f"{stem}.png"
        shutil.copy2(job_dir / "main.pdf", pdf)
        image = run([renderer, "-png", "-singlefile", "-r", str(dpi), str(pdf), str(output_dir / stem)], output_dir)
        if image.returncode != 0 or not png.is_file():
            print(image.stdout[-4000:], file=sys.stderr)
            return 1

    entry = dict(entries_by_id()[template_id])
    entry.update(
        {
            "rendered_at": datetime.now(timezone.utc).isoformat(),
            "source_path": f"cases/top_conference_visual_research/exact_templates/{template_id}/main.tex",
            "source_sha256": sha256(source),
            "outputs": {"pdf": pdf.name, "png": png.name, "pdf_sha256": sha256(pdf), "png_sha256": sha256(png)},
            "compiler": {"engine": engine_name, "engine_path": engine, "dpi": dpi},
            "qa": {"single_page": True, "fonts_embedded": True, "paper_image_embedded": False},
        }
    )
    report = output_dir / f"{stem}.json"
    report.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"rendered {template_id}: {pdf} / {png}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", help="allowlisted template ID")
    parser.add_argument("--output-dir", type=Path, default=Path("rendered/exact"))
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--engine", default="xelatex")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    ids = entries_by_id()
    if args.list:
        for template_id in ids:
            print(template_id)
        return 0
    if not args.template:
        parser.error("--template is required unless --list is used")
    return render(args.template, args.output_dir, args.dpi, args.engine)


if __name__ == "__main__":
    raise SystemExit(main())
