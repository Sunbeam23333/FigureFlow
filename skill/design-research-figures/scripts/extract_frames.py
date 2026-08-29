#!/usr/bin/env python3
"""Extract equally sized frames from a horizontal or vertical rollout strip."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops


def trim_uniform_border(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    difference = ImageChops.difference(rgb, background)
    bbox = difference.getbbox()
    return image.crop(bbox) if bbox else image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--axis", choices=("horizontal", "vertical"), default="horizontal")
    parser.add_argument("--gap", type=int, default=0, help="Pixels between frames")
    parser.add_argument("--trim", action="store_true", help="Trim uniform outer border first")
    parser.add_argument("--output-dir", type=Path, default=Path("frames"))
    parser.add_argument("--prefix", default="frame")
    args = parser.parse_args()

    if args.count < 1 or args.gap < 0:
        raise SystemExit("count must be >= 1 and gap must be >= 0")
    image = Image.open(args.input.expanduser().resolve()).convert("RGBA")
    if args.trim:
        image = trim_uniform_border(image)

    length = image.width if args.axis == "horizontal" else image.height
    available = length - args.gap * (args.count - 1)
    if available <= 0 or available % args.count:
        raise SystemExit(
            f"strip length {length} minus gaps is not evenly divisible by {args.count}"
        )
    frame_length = available // args.count
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for index in range(args.count):
        start = index * (frame_length + args.gap)
        if args.axis == "horizontal":
            box = (start, 0, start + frame_length, image.height)
        else:
            box = (0, start, image.width, start + frame_length)
        output = output_dir / f"{args.prefix}_{index:02d}.png"
        image.crop(box).save(output)
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
