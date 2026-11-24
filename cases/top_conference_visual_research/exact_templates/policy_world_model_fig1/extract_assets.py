#!/usr/bin/env python3
"""Extract the image-only evidence tiles from a locally supplied PWM PDF.

Coordinates are measured in 150-dpi page pixels on the official PDF's page 2.
The source PDF and extracted third-party images are deliberately not vendored.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from PIL import Image

TILES = {
    "observation_a": (296, 172, 377, 224),
    "observation_b": (470, 172, 550, 224),
    "state_prediction": (650, 174, 729, 225),
    "observation_c": (744, 172, 826, 224),
    "future_forecasting": (867, 186, 944, 226),
}
EXPECTED_PDF_SHA256 = "50b40d8aa3f5ff2f3bb64519e6d43145743838b55e529465346f8f62c20918f4"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    source_hash = hashlib.sha256(args.source_pdf.read_bytes()).hexdigest()
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError("Unexpected PDF hash: obtain the exact official proceedings PDF before cropping")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(["pdftoppm", "-f", "2", "-l", "2", "-singlefile", "-r", "150", "-png", str(args.source_pdf), str(prefix)], check=True)
        with Image.open(prefix.with_suffix(".png")) as page:
            if page.size != (1275, 1650):
                raise ValueError(f"Unexpected page dimensions: {page.size}; verify the source PDF")
            for name, box in TILES.items():
                page.crop(box).save(args.output_dir / f"{name}.png")
    manifest = {"source_pdf_sha256": source_hash,
                "source_url": "https://papers.neurips.cc/paper_files/paper/2025/file/c3b3c5f9297ad0012cfe7188c34cea0e-Paper-Conference.pdf",
                "page": 2, "dpi": 150, "boxes_px": TILES, "status": "published-figure",
                "tile_sha256": {name: hashlib.sha256((args.output_dir / f"{name}.png").read_bytes()).hexdigest() for name in TILES}}
    (args.output_dir / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

if __name__ == "__main__":
    main()
