#!/usr/bin/env python3
"""Rebuild the source-assisted diagram from a locally supplied paper PDF."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dpi", type=int, default=240)
    args = parser.parse_args()
    source = args.source_pdf.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(HERE / "extract_assets.py"), str(source), str(output / "assets")], check=True)
    shutil.copy2(HERE / "main.tex", output / "main.tex")
    subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"], cwd=output, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["pdftoppm", "-singlefile", "-png", "-r", str(args.dpi), str(output / "main.pdf"), str(output / "preview")], check=True)
    print(output / "main.pdf")


if __name__ == "__main__":
    main()
