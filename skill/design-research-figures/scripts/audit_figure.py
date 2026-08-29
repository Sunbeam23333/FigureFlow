#!/usr/bin/env python3
"""Report clipping risk by measuring non-background content near image edges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops

from public_safety import portable_path


def content_bbox(image: Image.Image, tolerance: int) -> tuple[int, int, int, int] | None:
    rgb = image.convert("RGB")
    samples = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)),
        rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    background_color = tuple(sum(pixel[channel] for pixel in samples) // 4 for channel in range(3))
    background = Image.new("RGB", rgb.size, background_color)
    difference = ImageChops.difference(rgb, background).convert("L")
    mask = difference.point(lambda value: 255 if value > tolerance else 0)
    return mask.getbbox()


def audit(
    path: Path,
    margin: int,
    tolerance: int,
    *,
    display_path: str | None = None,
) -> dict[str, object]:
    image = Image.open(path)
    bbox = content_bbox(image, tolerance)
    if bbox is None:
        distances = None
        risk = False
    else:
        left, top, right, bottom = bbox
        distances = {
            "left": left,
            "top": top,
            "right": image.width - right,
            "bottom": image.height - bottom,
        }
        risk = any(value < margin for value in distances.values())
    return {
        "file": display_path or path.name,
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "content_bbox": bbox,
        "edge_distances": distances,
        "margin_threshold": margin,
        "clipping_risk": risk,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--pattern", default="*.png")
    parser.add_argument("--margin", type=int, default=12)
    parser.add_argument("--tolerance", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    paths: list[Path] = []
    for raw in args.inputs:
        path = raw.expanduser().resolve()
        paths.extend(sorted(path.rglob(args.pattern)) if path.is_dir() else [path])
    report_base = Path.cwd().resolve()
    results = [
        audit(
            path,
            args.margin,
            args.tolerance,
            display_path=portable_path(path, report_base),
        )
        for path in paths
    ]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            status = "RISK" if result["clipping_risk"] else "OK"
            print(f"{status:4} {result['file']} edges={result['edge_distances']}")
    return 1 if any(result["clipping_risk"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
