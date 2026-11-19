#!/usr/bin/env python3
"""Render a pixel-faithful crop from a cited published PDF through a TikZ wrapper.

This is the source-locked route for figures containing photographic frames or
complex vector artwork. It requires the user to supply the cited PDF locally;
the PDF is never downloaded, committed, or silently embedded from a URL.
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

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "cases" / "top_conference_visual_research"
TEMPLATES = CASE / "exact_templates"
REGISTRY = TEMPLATES / "manifest.json"
CROP_REGISTRY = TEMPLATES / "reference_crop_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=180)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True)
    parser.add_argument("--source-pdf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("rendered/reference"))
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--engine", default="xelatex")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entry = next((item for item in registry["templates"] if item["template_id"] == args.template), None)
    crop_registry = json.loads(CROP_REGISTRY.read_text(encoding="utf-8"))["templates"]
    if entry is None or args.template not in crop_registry:
        print(f"error: unknown template ID: {args.template}", file=sys.stderr)
        return 2
    source_pdf = args.source_pdf.expanduser().resolve()
    if not source_pdf.is_file() or source_pdf.suffix.lower() != ".pdf":
        print("error: --source-pdf must be an existing PDF", file=sys.stderr)
        return 2
    pdftoppm = shutil.which("pdftoppm")
    engine = shutil.which(args.engine)
    if not pdftoppm or not engine:
        print("error: pdftoppm and xelatex are required", file=sys.stderr)
        return 2

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = crop_registry[args.template]
    bbox = spec["bbox"]
    with tempfile.TemporaryDirectory(prefix=f"figureflow-reference-{args.template}-") as temp:
        temp_dir = Path(temp)
        page_png = temp_dir / "page.png"
        render = run([pdftoppm, "-png", "-singlefile", "-r", str(args.dpi), "-f", str(spec["page"]), "-l", str(spec["page"]), str(source_pdf), str(temp_dir / "page")], temp_dir)
        if render.returncode != 0 or not page_png.is_file():
            print(render.stdout[-4000:], file=sys.stderr)
            return 1
        with Image.open(page_png) as page:
            width, height = page.size
            left, top, right, bottom = [float(value) for value in bbox]
            crop = page.crop((round(left * width), round(top * height), round(right * width), round(bottom * height))).convert("RGB")
            crop_path = temp_dir / "figure.png"
            crop.save(crop_path, optimize=True)
        wrapper = temp_dir / "wrapper.tex"
        wrapper.write_text(
            "\\documentclass[border=0pt]{standalone}\n"
            "\\usepackage{graphicx}\n"
            "\\begin{document}\n"
            "\\noindent\\includegraphics{figure.png}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        compile_result = run([engine, "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={temp_dir}", wrapper.name], temp_dir)
        if compile_result.returncode != 0 or not (temp_dir / "wrapper.pdf").is_file():
            print(compile_result.stdout[-4000:], file=sys.stderr)
            return 1
        pdf = output_dir / f"{args.template}_reference.pdf"
        png = output_dir / f"{args.template}_reference.png"
        shutil.copy2(temp_dir / "wrapper.pdf", pdf)
        shutil.copy2(crop_path, png)

    report = dict(entry)
    report.update({
        "fidelity": "source-locked crop",
        "source_pdf": source_pdf.name,
        "source_pdf_sha256": sha256(source_pdf),
        "source_page": spec["page"],
        "crop_bbox_normalized": bbox,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "outputs": {"pdf": pdf.name, "png": png.name, "pdf_sha256": sha256(pdf), "png_sha256": sha256(png)},
        "qa": {"source_artwork_preserved": True, "paper_screenshot_vendored": False, "tikz_wrapper": True},
    })
    (output_dir / f"{args.template}_reference.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"rendered source-locked {args.template}: {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
