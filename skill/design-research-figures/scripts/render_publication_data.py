"""Route the installed skill to FigureFlow's offline data/reproduction modules."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figureflow-root", type=Path, default=Path(__file__).resolve().parents[3])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", choices=["alphaedit-figure2"])
    source.add_argument("--csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=["annular", "small-multiples"], default="annular")
    parser.add_argument("--title", default="Model editing performance")
    parser.add_argument("--focus-method", default="AlphaEdit")
    args = parser.parse_args()
    root = args.figureflow_root.resolve()
    if not (root / "demo_core/alphaedit_reproduction.py").is_file():
        parser.error("This module needs the FigureFlow checkout; supply --figureflow-root /path/to/FigureFlow")
    if args.case:
        command = [sys.executable, "-m", "demo_core.alphaedit_reproduction"]
    else:
        command = [sys.executable, "-m", "demo_core.data_analysis", str(args.csv.resolve()),
                   "--kind", args.kind, "--title", args.title, "--focus-method", args.focus_method]
    command.extend(["--output-dir", str(args.output_dir.resolve())])
    subprocess.run(command, cwd=root, check=True)


if __name__ == "__main__":
    main()
