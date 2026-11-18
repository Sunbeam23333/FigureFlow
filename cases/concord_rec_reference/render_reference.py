#!/usr/bin/env python3
"""Re-render the retained CONCORD-Rec Figure 1/2 sources locally.

The two archived source files remain verbatim copies of the approved paper
renderers. This adapter only runs them with the small, local dependency bundle
kept beside the case and copies the resulting vector outputs into `reference/`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


CASE = Path(__file__).resolve().parent
SOURCES = CASE / "sources"
REFERENCE = CASE / "reference"


def _run(script: Path) -> None:
    subprocess.run([sys.executable, str(script)], cwd=str(CASE), check=True)


def main() -> None:
    REFERENCE.mkdir(parents=True, exist_ok=True)
    (CASE / "figures").mkdir(parents=True, exist_ok=True)
    _run(SOURCES / "figure1_architecture_render_v8.py")
    _run(SOURCES / "figure2_network_render_v4.py")

    outputs = {
        # v8 is retained as a reproducible base-layer generator; the approved
        # Figure 1 in reference/ is the later CO-F-original style refinement.
        "architecture_base_v8": SOURCES / "rendered",
        "network_structure": CASE / "figures",
    }
    for stem, folder in outputs.items():
        source_stem = "architecture" if stem == "architecture_base_v8" else stem
        for extension in ("svg", "pdf", "png", "json"):
            source = folder / f"{source_stem}.{extension}"
            if not source.is_file():
                raise FileNotFoundError(source)
            shutil.copy2(source, REFERENCE / f"{stem}.{extension}")
    print("Rendered CONCORD-Rec Figure 1/2 into", REFERENCE)


if __name__ == "__main__":
    main()
