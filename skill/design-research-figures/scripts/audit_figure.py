#!/usr/bin/env python3
"""Report clipping risk by measuring non-background content near image edges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

from public_safety import portable_path


def estimated_background(image: Image.Image, model: str) -> Image.Image:
    """Estimate only an allowlisted page background; foreground residuals remain visible."""
    rgb = image.convert("RGB")
    top_left = np.asarray(rgb.getpixel((0, 0)), dtype=np.float32)
    top_right = np.asarray(rgb.getpixel((rgb.width - 1, 0)), dtype=np.float32)
    bottom_left = np.asarray(rgb.getpixel((0, rgb.height - 1)), dtype=np.float32)
    bottom_right = np.asarray(rgb.getpixel((rgb.width - 1, rgb.height - 1)), dtype=np.float32)
    if model == "solid-corners":
        background_color = tuple(
            int(value) for value in np.mean([top_left, top_right, bottom_left, bottom_right], axis=0)
        )
        return Image.new("RGB", rgb.size, background_color)
    if model != "bilinear-corners":
        raise ValueError(f"unsupported background model: {model}")
    x = np.linspace(0.0, 1.0, rgb.width, dtype=np.float32)[None, :, None]
    y = np.linspace(0.0, 1.0, rgb.height, dtype=np.float32)[:, None, None]
    top = top_left[None, None, :] * (1.0 - x) + top_right[None, None, :] * x
    bottom = bottom_left[None, None, :] * (1.0 - x) + bottom_right[None, None, :] * x
    plane = top * (1.0 - y) + bottom * y
    return Image.fromarray(np.clip(np.rint(plane), 0, 255).astype(np.uint8))


def content_bbox(
    image: Image.Image,
    tolerance: int,
    background_model: str = "solid-corners",
) -> tuple[int, int, int, int] | None:
    rgb = image.convert("RGB")
    background = estimated_background(rgb, background_model)
    difference = ImageChops.difference(rgb, background).convert("L")
    mask = difference.point(lambda value: 255 if value > tolerance else 0)
    return mask.getbbox()


def audit(
    path: Path,
    margin: int,
    tolerance: int,
    *,
    display_path: str | None = None,
    background_model: str = "solid-corners",
) -> dict[str, object]:
    image = Image.open(path)
    bbox = content_bbox(image, tolerance, background_model)
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
        "background_model": background_model,
        "clipping_risk": risk,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--pattern", default="*.png")
    parser.add_argument("--margin", type=int, default=12)
    parser.add_argument("--tolerance", type=int, default=8)
    parser.add_argument(
        "--background-model",
        choices=("solid-corners", "bilinear-corners"),
        default="solid-corners",
    )
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
            background_model=args.background_model,
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
