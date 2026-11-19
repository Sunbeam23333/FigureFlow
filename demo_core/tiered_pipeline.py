"""Reusable contract for the FigureFlow tiered-pipeline grammar.

The reference FigureFlow/PPT case is a grid-first composition rather than a
free-form AI canvas: three source modules feed three evidence modules, the
branches converge into one shared artifact, and a full-width training band
feeds a compact application row.  This module keeps that geometry and the
PPT-style assembly steps machine-checkable while leaving the case-specific
SVG primitives in the demo renderer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = ROOT / "skill" / "design-research-figures" / "assets" / "layouts" / "tiered_pipeline_reference.json"
LAYOUT_ID = "tiered_pipeline_reference"
REQUIRED_SPEC_KEYS = {
    "id", "background", "case", "case_caption", "top_middle", "top_right", "observe",
    "states", "state_band", "middle_left", "middle_mid", "middle_right", "timeline_caption",
    "timeline_body", "pair_caption", "decision_left", "decision_right", "decision_caption",
    "shared_title", "shared_fields", "training_title", "loss_label", "application_title",
    "application_embedding", "application_left", "application_right",
}


class TieredPipelineError(ValueError):
    """Raised when a tiered case does not satisfy the bounded contract."""


def load_layout(path: Path = LAYOUT_PATH) -> dict[str, Any]:
    """Load and validate the checked-in reference geometry."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("id") != LAYOUT_ID:
        raise TieredPipelineError("unexpected tiered layout id")
    canvas = payload.get("canvas", {})
    if canvas.get("width") != 1600 or canvas.get("height") != 1298:
        raise TieredPipelineError("tiered layout must remain 1600x1298")
    if payload.get("connectors", {}).get("style") != "orthogonal":
        raise TieredPipelineError("tiered layout requires orthogonal connectors")
    if payload.get("connectors", {}).get("avoid_curved_flow_arcs") is not True:
        raise TieredPipelineError("tiered layout must forbid curved flow arcs")
    return payload


def _short_text(value: Any, field: str, limit: int = 90) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise TieredPipelineError(f"{field} must be a non-empty string of at most {limit} characters")
    return value.strip()


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a case spec without executing model-authored code or paths."""
    if not isinstance(spec, dict):
        raise TieredPipelineError("case spec must be an object")
    missing = REQUIRED_SPEC_KEYS - set(spec)
    if missing:
        raise TieredPipelineError(f"case spec is missing keys: {sorted(missing)}")
    _short_text(spec["id"], "id", 80)
    for field in REQUIRED_SPEC_KEYS - {"observe", "states", "timeline_body"}:
        _short_text(spec[field], field)
    if not isinstance(spec["observe"], list) or len(spec["observe"]) != 3:
        raise TieredPipelineError("observe must contain exactly three semantic inputs")
    if not isinstance(spec["states"], list) or len(spec["states"]) != 3:
        raise TieredPipelineError("states must contain exactly three state modules")
    if not isinstance(spec["timeline_body"], list) or not 1 <= len(spec["timeline_body"]) <= 3:
        raise TieredPipelineError("timeline_body must contain one to three lines")
    for item in spec["observe"]:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise TieredPipelineError("observe entries must be [icon, label, detail]")
        for value in item:
            _short_text(value, "observe entry", 40)
    for item in spec["states"]:
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            raise TieredPipelineError("state entries must be [icon, label, detail-lines, color]")
        icon, label, details, color = item
        _short_text(icon, "state icon", 20)
        _short_text(label, "state label", 32)
        if not isinstance(details, (list, tuple)) or not 1 <= len(details) <= 2:
            raise TieredPipelineError("state detail must contain one or two lines")
        for detail in details:
            _short_text(detail, "state detail", 48)
        _short_text(color, "state color", 16)
    return spec


def output_manifest_entry(spec: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Return a portable provenance entry for a rendered case."""
    validate_spec(spec)
    source_names = [spec["case"], *spec.get("extra", [])]
    return {
        "id": spec["id"],
        "status": "illustrative",
        "case": spec["case"],
        "background": f"generated/{spec['background']}",
        "background_used_in_layout": False,
        "layout": LAYOUT_ID,
        "native_text": True,
        "connectors": "orthogonal",
        "case_caption": spec["case_caption"],
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in source_names
            if (root / name).is_file()
        },
    }


def write_outputs(
    svg: str,
    svg_path: Path,
    pdf_path: Path,
    png_path: Path,
    *,
    width: int = 1600,
    height: int = 1298,
    pdf_width_pt: float = 540,
    review_png_path: Path | None = None,
) -> None:
    """Write SVG/PDF/PNG from one current SVG source.

    The SVG/PNG preserve the source canvas.  The PDF is deliberately emitted
    at the reference paper include width (540 pt) so page-level QA exercises
    the typography at the size a reader will actually see.
    """
    import cairosvg

    svg_path.write_text(svg, encoding="utf-8")
    # CairoSVG interprets output dimensions as CSS pixels (96 dpi), while
    # PDF metadata is expressed in points (72 dpi).
    pdf_width_px = pdf_width_pt * 96 / 72
    pdf_height_px = pdf_width_px * height / width
    cairosvg.svg2pdf(
        bytestring=svg.encode("utf-8"),
        write_to=str(pdf_path),
        output_width=pdf_width_px,
        output_height=pdf_height_px,
    )
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), output_width=width, output_height=height)
    if review_png_path is not None:
        review_width = round(pdf_width_pt * 240 / 72)
        review_height = round(review_width * height / width)
        cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            write_to=str(review_png_path),
            output_width=review_width,
            output_height=review_height,
        )
