#!/usr/bin/env python3
"""Build the exact-template contact-sheet PDF used for visual QA."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent
TEMPLATES = CASE / "exact_templates"
RENDERER = ROOT / "skill" / "design-research-figures" / "scripts" / "render_exact_template.py"
OUT = CASE / "figureflow_exact_reproduction_atlas.pdf"


def main() -> int:
    payload = json.loads((TEMPLATES / "manifest.json").read_text(encoding="utf-8"))
    entries = payload["templates"]
    width, height = 1654, 1169
    try:
        font_bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
        font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
        font_small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
    except OSError:
        font_bold = font_title = font_small = ImageFont.load_default()
    with tempfile.TemporaryDirectory(prefix="figureflow-atlas-") as temp:
        render_dir = Path(temp) / "renders"
        render_dir.mkdir()
        images: list[tuple[dict, Path]] = []
        for entry in entries:
            subprocess.run(
                [sys.executable, str(RENDERER), "--template", entry["template_id"], "--output-dir", str(render_dir), "--dpi", "130"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            images.append((entry, render_dir / f"{entry['template_id']}.png"))

        pages: list[Image.Image] = []
        for page_index in range(0, len(images), 2):
            page = Image.new("RGB", (width, height), "#F7F9FC")
            draw = ImageDraw.Draw(page)
            draw.text((28, 24), "FigureFlow exact-template atlas", fill="#17324D", font=font_bold)
            draw.text((28, 62), "Native TikZ/PGFPlots derived reproductions • layout-faithful • no paper screenshots vendored", fill="#667085", font=font_small)
            for row, (entry, image_path) in enumerate(images[page_index : page_index + 2]):
                card_x, card_y, card_w, card_h = 24, 95 + row * 500, width - 48, 450
                draw.rounded_rectangle((card_x, card_y, card_x + card_w, card_y + card_h), radius=12, fill="#FFFFFF", outline="#D9E0E8", width=2)
                with Image.open(image_path) as image:
                    preview = image.convert("RGB")
                preview.thumbnail((card_w - 26, 348))
                page.paste(preview, (card_x + (card_w - preview.width) // 2, card_y + 30 + (348 - preview.height) // 2))
                draw.text((card_x + 14, card_y + card_h - 34), entry["template_id"], fill="#263238", font=font_title)
                draw.text((card_x + 225, card_y + card_h - 33), f"{entry['paper']} • {entry['figure_id']} • p.{entry['source_page']}", fill="#667085", font=font_small)
                x = card_x + card_w - 190
                for name, value in entry.get("palette", {}).items():
                    if not isinstance(value, str) or not value.startswith("#"):
                        continue
                    draw.ellipse((x, card_y + card_h - 30, x + 9, card_y + card_h - 21), fill=value)
                    x += 10
            draw.text((width - 180, 28), f"FigureFlow • page {page_index // 2 + 1}", fill="#98A2B3", font=font_small)
            pages.append(page)
        pages[0].save(OUT, save_all=True, append_images=pages[1:], resolution=150.0)
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
