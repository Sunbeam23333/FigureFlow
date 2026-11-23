"""Validate and query the source-locked main-figure research registry.

This registry is intentionally separate from the generic FigurePlan workflow.
It describes published-paper evidence and the native reproduction route without
claiming that a TikZ sketch is pixel-identical to the paper artwork.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "cases" / "top_conference_visual_research" / "exact_templates" / "replication_registry.json"
ALLOWED_RENDERERS = {"native-tikz", "source-locked-pdf", "native-data-replot"}
ALLOWED_FIDELITY = {"layout-faithful", "pixel-faithful-crop", "data-driven-replot"}


class MainFigureRegistryError(ValueError):
    """Raised when the research registry is malformed or incomplete."""


def _https_url(value: Any, field: str) -> None:
    parsed = urlparse(str(value))
    if parsed.scheme != "https" or not parsed.netloc:
        raise MainFigureRegistryError(f"{field} must be an absolute HTTPS URL")


def _bbox(value: Any, field: str) -> None:
    if not isinstance(value, list) or len(value) != 4 or not all(isinstance(v, (int, float)) for v in value):
        raise MainFigureRegistryError(f"{field} must be [x0, y0, x1, y1]")
    x0, y0, x1, y1 = value
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise MainFigureRegistryError(f"{field} must be normalized and strictly ordered")


def validate_registry(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a registry and return it unchanged for safe querying."""
    if not isinstance(payload, dict) or payload.get("schema_version") != "mainfigure-replication-1":
        raise MainFigureRegistryError("unsupported mainfigure registry schema")
    templates = payload.get("templates")
    if not isinstance(templates, list) or not templates:
        raise MainFigureRegistryError("registry must contain a non-empty templates list")
    ids: set[str] = set()
    for entry in templates:
        if not isinstance(entry, dict):
            raise MainFigureRegistryError("each registry entry must be an object")
        template_id = entry.get("template_id")
        if not isinstance(template_id, str) or not template_id or template_id in ids:
            raise MainFigureRegistryError("template IDs must be unique non-empty strings")
        ids.add(template_id)
        source = entry.get("source", {})
        for key in ("paper", "conference", "figure_id", "source_url"):
            if not source.get(key):
                raise MainFigureRegistryError(f"{template_id}: source.{key} is required")
        _https_url(source["source_url"], f"{template_id}.source_url")
        if not isinstance(source.get("year"), int) or source["year"] < 2000:
            raise MainFigureRegistryError(f"{template_id}: source.year is invalid")
        if not isinstance(source.get("page"), int) or source["page"] < 1:
            raise MainFigureRegistryError(f"{template_id}: source.page is invalid")
        crop = entry.get("crop", {})
        _bbox(crop.get("bbox"), f"{template_id}.crop.bbox")
        if crop.get("coordinate_system") != "normalized-page-top-left":
            raise MainFigureRegistryError(f"{template_id}: crop coordinate system is not explicit")
        grammar = entry.get("grammar", {})
        if grammar.get("renderer") not in ALLOWED_RENDERERS:
            raise MainFigureRegistryError(f"{template_id}: unsupported renderer")
        if grammar.get("fidelity") not in ALLOWED_FIDELITY:
            raise MainFigureRegistryError(f"{template_id}: unsupported fidelity boundary")
        if not grammar.get("layout_family") or not grammar.get("reading_order"):
            raise MainFigureRegistryError(f"{template_id}: grammar must define layout and reading order")
        visual = entry.get("visual", {})
        if not isinstance(visual.get("palette"), dict) or not visual["palette"]:
            raise MainFigureRegistryError(f"{template_id}: palette is required")
        if not visual.get("typography"):
            raise MainFigureRegistryError(f"{template_id}: typography is required")
        evidence = entry.get("evidence", {})
        if evidence.get("status") != "published-figure" or not evidence.get("boundary"):
            raise MainFigureRegistryError(f"{template_id}: evidence status/boundary is required")
        qa = entry.get("qa", {})
        if qa.get("paper_include_width_pt") != 540 or qa.get("source_locked_crop") is not True:
            raise MainFigureRegistryError(f"{template_id}: paper-width/source-lock QA contract is incomplete")
    return payload


def load_mainfigure_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    return validate_registry(json.loads(path.read_text(encoding="utf-8")))


def get_mainfigure(template_id: str, *, path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    for entry in load_mainfigure_registry(path)["templates"]:
        if entry["template_id"] == template_id:
            return entry
    raise KeyError(template_id)


def list_mainfigures(*, conference: str | None = None, role: str | None = None, path: Path = DEFAULT_REGISTRY) -> list[dict[str, Any]]:
    entries = load_mainfigure_registry(path)["templates"]
    return [
        entry for entry in entries
        if (conference is None or entry["source"]["conference"].casefold() == conference.casefold())
        and (role is None or entry["grammar"].get("role") == role)
    ]
