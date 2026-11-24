#!/usr/bin/env python3
"""Make a visual comparison without claiming an automatic fidelity score.

The reference and candidate are independently fitted without cropping or
distorting.  An optional overlay reveals registration/layout disagreements;
it is a diagnostic, not evidence that the underlying data have been reproduced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def compare(reference: Path, candidate: Path, output: Path) -> None:
    with Image.open(reference) as im:
        ref = fit(im, (1400, 1050))
    with Image.open(candidate) as im:
        cand = fit(im, (1400, 1050))
    canvas = Image.new("RGB", (2880, 1170), "#f1f3f5")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    for x, label, im in [(20, "REFERENCE (published figure)", ref), (1460, "CANDIDATE (editable reconstruction)", cand)]:
        draw.text((x + 10, 15), label, font=font, fill="#222222")
        draw.rectangle((x, 65, x + 1400, 1115), fill="white", outline="#c9cdd1", width=2)
        canvas.paste(im, (x + (1400 - im.width) // 2, 65 + (1050 - im.height) // 2))
    draw.text((30, 1130), "Compare layout, text, imagery and data manually; matching a crop is not editable reconstruction.", font=font, fill="#333333")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    manifest = {
        "reference_file": reference.name, "reference_sha256": digest(reference),
        "candidate_file": candidate.name, "candidate_sha256": digest(candidate),
        "comparison_file": output.name, "comparison_sha256": digest(output),
        "fidelity": "not assessed automatically", "method": "side-by-side; aspect ratios preserved",
    }
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compare(args.reference, args.candidate, args.output)


if __name__ == "__main__":
    main()
