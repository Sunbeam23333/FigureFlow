#!/usr/bin/env python3
"""Create a labeled contact sheet for figure candidates."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def discover(folder: Path, pattern: str) -> list[Path]:
    return sorted(path for path in folder.rglob(pattern) if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--pattern", default="*.png")
    parser.add_argument("--output", type=Path, default=Path("gallery.png"))
    parser.add_argument("--columns", type=int, default=2)
    parser.add_argument("--cell-width", type=int, default=1200)
    parser.add_argument("--padding", type=int, default=36)
    parser.add_argument("--label-height", type=int, default=56)
    parser.add_argument("--background", default="#F7F8F6")
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    paths = [
        path
        for path in discover(args.input_dir.expanduser().resolve(), args.pattern)
        if path.resolve() != output
    ]
    if not paths:
        raise SystemExit("no matching images found")
    if args.columns < 1 or args.cell_width < 100:
        raise SystemExit("columns must be >= 1 and cell-width >= 100")

    opened: list[Image.Image] = []
    for path in paths:
        image = Image.open(path).convert("RGBA")
        flattened = Image.new("RGBA", image.size, args.background)
        flattened.alpha_composite(image)
        opened.append(flattened.convert("RGB"))
    scaled: list[Image.Image] = []
    cell_heights: list[int] = []
    for image in opened:
        scale = args.cell_width / image.width
        resized = image.resize(
            (args.cell_width, max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        scaled.append(resized)
        cell_heights.append(resized.height + args.label_height)

    rows = math.ceil(len(scaled) / args.columns)
    row_heights = [
        max(cell_heights[row * args.columns : (row + 1) * args.columns])
        for row in range(rows)
    ]
    width = args.columns * args.cell_width + (args.columns + 1) * args.padding
    height = sum(row_heights) + (rows + 1) * args.padding
    canvas = Image.new("RGB", (width, height), args.background)
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        font = ImageFont.load_default()

    y = args.padding
    for row in range(rows):
        x = args.padding
        for col in range(args.columns):
            index = row * args.columns + col
            if index >= len(scaled):
                break
            image = scaled[index]
            canvas.paste(image, (x, y + args.label_height))
            draw.text((x, y + 10), paths[index].stem, fill="#1A1A1A", font=font)
            x += args.cell_width + args.padding
        y += row_heights[row] + args.padding

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    print(f"wrote {output} ({len(paths)} candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
