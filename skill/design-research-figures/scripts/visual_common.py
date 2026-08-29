#!/usr/bin/env python3
"""Shared style, I/O, and rendering helpers for research-paper visuals."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_CACHE_ROOT = Path(tempfile.gettempdir()) / "design-research-figures-cache"
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_CACHE_ROOT / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_ROOT / "xdg"))

import matplotlib as mpl
import yaml

mpl.use("Agg", force=True)


THEME_PATH = Path(__file__).resolve().parent.parent / "assets" / "themes" / "academic_audit.json"
THEME = json.loads(THEME_PATH.read_text(encoding="utf-8"))
PALETTE: dict[str, str] = THEME["palette"]
EVIDENCE_STATUSES = {
    "measured",
    "implemented",
    "simulation",
    "forecast",
    "illustrative",
    "synthetic-demo",
    "failed-gate",
}


def color(value: str | None, default: str = "navy") -> str:
    if value is None:
        value = default
    return PALETTE.get(value, value)


def configure_matplotlib(*, display: bool = False) -> None:
    mpl.rcParams.update(
        {
            "font.family": THEME["typography"]["display"] if display else THEME["typography"]["quantitative"],
            "font.size": 8.5,
            "axes.titlesize": 10.3,
            "axes.labelsize": 8.5,
            "legend.fontsize": 7.3,
            "xtick.labelsize": 7.4,
            "ytick.labelsize": 7.4,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "axes.edgecolor": PALETTE["navy"],
            "text.color": PALETTE["navy"],
            "axes.labelcolor": PALETTE["navy"],
            "xtick.color": PALETTE["gray"],
            "ytick.color": PALETTE["gray"],
            "pdf.fonttype": THEME["render"]["pdf_fonttype"],
            "ps.fonttype": THEME["render"]["pdf_fonttype"],
            "svg.fonttype": "none",
        }
    )


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a mapping in {path}")
    return data


def resolve_from(spec_path: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (spec_path.parent / path).resolve()


def save_figure(fig, output_stem: Path, *, dpi: int = 240) -> tuple[Path, Path]:
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    pdf = output_stem.with_suffix(".pdf")
    png = output_stem.with_suffix(".png")
    fig.savefig(pdf, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(png, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    return pdf, png


def render_pdf(pdf: Path, png: Path, *, dpi: int = 220) -> None:
    renderer = shutil.which("pdftoppm")
    if not renderer:
        raise RuntimeError("pdftoppm is required to render review PNGs")
    prefix = png.with_suffix("")
    result = subprocess.run(
        [renderer, "-png", "-singlefile", "-r", str(dpi), str(pdf), str(prefix)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"pdftoppm failed for {pdf}:\n{result.stdout}")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_artifact_manifest(
    output_stem: Path,
    spec_path: Path,
    spec: dict[str, Any],
    outputs: list[Path] | tuple[Path, ...],
    *,
    inputs: list[Path] | tuple[Path, ...] = (),
) -> Path:
    evidence_status = spec.get("evidence_status")
    if evidence_status not in EVIDENCE_STATUSES:
        allowed = ", ".join(sorted(EVIDENCE_STATUSES))
        raise ValueError(f"spec needs evidence_status in {{{allowed}}}")
    all_outputs = [Path(path).resolve() for path in outputs]
    all_inputs = [Path(spec_path).resolve(), *(Path(path).resolve() for path in inputs)]
    manifest = {
        "id": output_stem.name,
        "evidence_status": evidence_status,
        "visible_status": spec.get("status"),
        "source_spec": str(Path(spec_path).resolve()),
        "inputs": [str(path) for path in all_inputs],
        "outputs": [str(path) for path in all_outputs],
        "sha256": {path.name: file_sha256(path) for path in all_outputs if path.is_file()},
    }
    path = output_stem.with_name(f"{output_stem.name}_manifest.json")
    write_json(path, manifest)
    return path


def status_colors(kind: str) -> tuple[str, str, str]:
    if kind == "measured":
        return color("teal"), color("light_teal"), "#B6DDD6"
    if kind == "implemented":
        return color("blue"), color("light_blue"), "#B8D4EC"
    if kind == "simulation":
        return color("violet"), color("light_violet"), "#D4C2E3"
    if kind == "failed-gate":
        return color("red"), color("light_red"), "#E7B7AA"
    if kind in {"warning", "forecast", "illustrative", "synthetic-demo"}:
        return "#9A5215", color("light_orange"), "#F2C48D"
    return "#9A5215", color("light_orange"), "#F2C48D"
