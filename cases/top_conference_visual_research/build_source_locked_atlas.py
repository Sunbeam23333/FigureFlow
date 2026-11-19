#!/usr/bin/env python3
"""Build a source-locked atlas from locally supplied official paper PDFs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent
TEMPLATES = CASE / "exact_templates"
RENDERER = ROOT / "skill" / "design-research-figures" / "scripts" / "render_reference_figure.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=CASE / "figureflow_source_locked_atlas.pdf")
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()
    source_dir = args.source_dir.expanduser().resolve()
    mapping = json.loads((TEMPLATES / "source_pdf_map.json").read_text(encoding="utf-8"))
    registry = json.loads((TEMPLATES / "manifest.json").read_text(encoding="utf-8"))
    if any(not (source_dir / name).is_file() for name in mapping.values()):
        missing = [name for name in mapping.values() if not (source_dir / name).is_file()]
        parser.error(f"missing source PDFs: {', '.join(missing)}")
    try:
        bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    except OSError:
        bold = small = ImageFont.load_default()
    pages: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="figureflow-source-atlas-") as temp:
        render_dir = Path(temp)
        for page_start in range(0, len(registry["templates"]), 2):
            page = Image.new("RGB", (1654, 1169), "#F7F9FC")
            draw = ImageDraw.Draw(page)
            draw.text((28, 24), "FigureFlow source-locked atlas", fill="#17324D", font=bold)
            draw.text((28, 62), "Exact crop from the cited published PDF • source hash recorded per output", fill="#667085", font=small)
            for row, entry in enumerate(registry["templates"][page_start : page_start + 2]):
                name = entry["template_id"]
                out_dir = render_dir / name
                out_dir.mkdir()
                subprocess.run([sys.executable, str(RENDERER), "--template", name, "--source-pdf", str(source_dir / mapping[name]), "--output-dir", str(out_dir), "--dpi", str(args.dpi)], cwd=ROOT, check=True, capture_output=True, text=True)
                with Image.open(out_dir / f"{name}_reference.png") as image:
                    preview = image.convert("RGB")
                preview.thumbnail((1570, 410))
                card_y = 95 + row * 500
                draw.rounded_rectangle((24, card_y, 1630, card_y + 450), radius=12, fill="#FFFFFF", outline="#D9E0E8", width=2)
                page.paste(preview, (24 + (1606 - preview.width) // 2, card_y + 16 + (410 - preview.height) // 2))
                draw.text((38, card_y + 420), f"{name} • {entry['paper']} • {entry['figure_id']} • p.{entry['source_page']}", fill="#263238", font=small)
            pages.append(page)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(args.output, save_all=True, append_images=pages[1:], resolution=150.0)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
