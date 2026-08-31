#!/usr/bin/env python3
"""Render a Chinese-friendly, asset-aware workflow figure from a safe JSON plan."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import platform
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import cairosvg
from PIL import Image


WIDTH, HEIGHT = 1800, 1000


def default_font_family() -> str:
    """Use one concrete CJK family because CairoSVG does not reliably fall back."""
    configured = os.getenv("FIGUREFLOW_FONT_FAMILY")
    if configured:
        return configured
    system = platform.system()
    if system == "Darwin":
        return "Arial Unicode MS"
    if system == "Windows":
        return "Microsoft YaHei"
    return "Noto Sans CJK SC"


FONT = default_font_family()
THEME_DIR = Path(__file__).resolve().parent.parent / "assets" / "themes"
THEME_FILES = {
    "academic-audit": THEME_DIR / "academic_audit.json",
    "gpu-green-tech": THEME_DIR / "gpu_green_tech.json",
}
SAFE_ASSET_KEYS = {
    "layout_planner",
    "icon_factory",
    "chroma_matte",
    "vector_typeset",
    "qa_export",
    "gpu_server",
    "robot_inspection",
    "data",
    "process",
    "decision",
    "store",
    "output",
}
SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SAFE_REFERENCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
SAFE_PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
REFERENCE_FIELDS = {
    "id",
    "title",
    "uri",
    "source_type",
    "provider",
    "media_type",
    "source_url",
    "author",
    "license_name",
    "license_url",
    "attribution",
}
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class WorkflowTheme:
    name: str
    palette: dict[str, str]
    light: dict[str, str]
    surface: dict[str, str]
    source_path: Path


def load_theme(name: str) -> WorkflowTheme:
    """Load one allowlisted token file and fail closed on incomplete colors."""
    try:
        source_path = THEME_FILES[name]
    except KeyError as exc:
        raise ValueError(f"unsupported workflow theme: {name}") from exc
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    palette_source = payload.get("palette", {})
    workflow = payload.get("workflow", {})
    palette_keys = ("navy", "blue", "teal", "orange", "violet", "red", "gray", "line", "paper")
    surface_keys = (
        "background_start",
        "background_mid",
        "background_end",
        "decoration_primary",
        "decoration_secondary",
        "card",
        "card_border",
        "rail",
        "shadow",
    )
    palette = {key: str(palette_source.get(key, "")) for key in palette_keys}
    palette["white"] = str(workflow.get("card", ""))
    light = {
        "navy": str(palette_source.get("light_blue", "")),
        "blue": str(palette_source.get("light_blue", "")),
        "teal": str(palette_source.get("light_teal", "")),
        "orange": str(palette_source.get("light_orange", "")),
        "violet": str(palette_source.get("light_violet", "")),
        "red": str(palette_source.get("light_red", "")),
        "gray": str(palette_source.get("predgray", "")),
    }
    surface = {key: str(workflow.get(key, "")) for key in surface_keys}
    values = [*palette.values(), *light.values(), *surface.values()]
    if payload.get("id") != name or not all(HEX_COLOR.fullmatch(value) for value in values):
        raise ValueError(f"workflow theme token file is incomplete or invalid: {source_path.name}")
    return WorkflowTheme(name=name, palette=palette, light=light, surface=surface, source_path=source_path)


DEFAULT_THEME = load_theme("academic-audit")
PALETTE = DEFAULT_THEME.palette
LIGHT = DEFAULT_THEME.light
STATUS_TEXT = {
    "measured": "实测",
    "implemented": "已实现",
    "simulation": "仿真",
    "forecast": "预测",
    "illustrative": "示意",
    "synthetic-demo": "合成演示",
    "failed-gate": "未达门槛",
}
STATUS_COLOR = {
    "measured": "teal",
    "implemented": "teal",
    "simulation": "blue",
    "forecast": "orange",
    "illustrative": "gray",
    "synthetic-demo": "orange",
    "failed-gate": "red",
}
ALLOWED_LAYOUTS = {"ribbon", "bowtie", "dual-rail"}
ALLOWED_LAYOUT_PRESETS = {"standard", "presentation-spacious"}
ALLOWED_ACCENTS = {"navy", "blue", "teal", "orange", "violet"}
ALLOWED_STATUSES = set(STATUS_TEXT)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rounded(x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", radius: float = 22, sw: float = 1.2) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'rx="{radius:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"/>'
    )


def text(
    x: float,
    y: float,
    value: str,
    size: float,
    *,
    weight: int = 500,
    fill: str | None = None,
    anchor: str = "start",
    opacity: float = 1.0,
    theme: WorkflowTheme = DEFAULT_THEME,
) -> str:
    fill = fill or theme.palette["navy"]
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size:.1f}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" opacity="{opacity:.3f}">{escape(str(value))}</text>'
    )


def char_units(char: str) -> float:
    if char.isspace():
        return 0.6
    return 2.0 if unicodedata.east_asian_width(char) in {"W", "F"} else 1.0


def wrap_text(value: str, max_units: float, max_lines: int) -> list[str]:
    """Wrap Chinese and mixed text without depending on whitespace."""
    lines: list[str] = []
    current: list[str] = []
    units = 0.0
    forbidden_starts = set("，。！？；：、）》】」』”’％,.!?;:%)")
    for char in value.strip():
        width = char_units(char)
        if current and units + width > max_units:
            if char in forbidden_starts and len(current) > 1:
                current.append(char)
                char = ""
            lines.append("".join(current).strip())
            current = []
            units = 0.0
            if len(lines) >= max_lines:
                break
        if char:
            current.append(char)
            units += width
    if current and len(lines) < max_lines:
        lines.append("".join(current).strip())
    consumed = "".join(lines).replace(" ", "")
    source = value.strip().replace(" ", "")
    if consumed != source and lines:
        lines[-1] = lines[-1].rstrip("… .") + "…"
    return lines or [""]


def require_text(value: Any, label: str, *, max_units: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise ValueError(f"{label} contains an unsupported control character")
    if sum(char_units(char) for char in value) > max_units:
        raise ValueError(f"{label} exceeds the display-width budget")
    return value


def validate_reference_uri(
    value: Any,
    label: str,
    *,
    allowed_schemes: set[str],
) -> str:
    """Validate metadata-only links without allowing signed queries into manifests."""
    uri = require_text(value, label, max_units=4096)
    if len(uri) > 2048:
        raise ValueError(f"{label} exceeds the length limit")
    parsed = urlsplit(uri)
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        choices = ", ".join(sorted(allowed_schemes))
        raise ValueError(f"{label} must use one of these schemes: {choices}")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} may not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} may not contain a query string or fragment")
    return uri


def validate_plan(plan: dict[str, Any]) -> None:
    """Validate the standalone CLI contract without importing the demo package."""
    require_text(plan.get("title"), "title", max_units=60)
    require_text(plan.get("takeaway"), "takeaway", max_units=180)
    require_text(plan.get("status_label"), "status_label", max_units=30)
    require_text(plan.get("caption"), "caption", max_units=360)
    if plan.get("layout_family", "ribbon") not in ALLOWED_LAYOUTS:
        raise ValueError("unsupported layout family")
    if plan.get("layout_preset", "standard") not in ALLOWED_LAYOUT_PRESETS:
        raise ValueError("unsupported layout preset")
    if plan.get("theme", "academic-audit") not in THEME_FILES:
        raise ValueError("unsupported workflow theme")
    if plan.get("evidence_status") not in ALLOWED_STATUSES:
        raise ValueError("unsupported evidence status")
    stages = plan.get("stages")
    if not isinstance(stages, list) or not 3 <= len(stages) <= 6:
        raise ValueError("workflow requires 3–6 stages")
    seen_titles: set[str] = set()
    seen_assets: set[str] = set()
    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            raise ValueError(f"stage {index} must be an object")
        title = require_text(stage.get("title"), f"stage {index} title", max_units=24)
        require_text(stage.get("subtitle"), f"stage {index} subtitle", max_units=28)
        if title in seen_titles:
            raise ValueError("stage titles must be unique")
        seen_titles.add(title)
        asset_key = stage.get("asset_key", "process")
        if asset_key not in SAFE_ASSET_KEYS:
            raise ValueError(f"unsupported asset key: {asset_key!r}")
        if asset_key in seen_assets:
            raise ValueError("each stage must use a distinct semantic asset key")
        seen_assets.add(asset_key)
        if stage.get("accent", "blue") not in ALLOWED_ACCENTS:
            raise ValueError("unsupported stage accent")
        if stage.get("evidence_status", "illustrative") not in ALLOWED_STATUSES:
            raise ValueError("unsupported stage evidence status")
        body = stage.get("body", [])
        if not isinstance(body, list) or len(body) > 3:
            raise ValueError("stage body must contain at most three lines")
        if plan.get("layout_preset", "standard") == "presentation-spacious" and len(body) > 2:
            raise ValueError("presentation-spacious permits at most two body lines per stage")
        for body_index, line in enumerate(body, start=1):
            require_text(line, f"stage {index} body {body_index}", max_units=24)
    gates = plan.get("gates", [])
    warnings = plan.get("warnings", [])
    if not isinstance(gates, list) or len(gates) > 5:
        raise ValueError("gates must contain at most five labels")
    if not isinstance(warnings, list) or len(warnings) > 6:
        raise ValueError("warnings must contain at most six items")
    for index, label in enumerate(gates, start=1):
        require_text(label, f"gate {index}", max_units=20)
    for index, warning in enumerate(warnings, start=1):
        require_text(warning, f"warning {index}", max_units=160)
    references = plan.get("reference_assets", [])
    if not isinstance(references, list) or len(references) > 8:
        raise ValueError("reference_assets must contain at most eight entries")
    reference_ids: set[str] = set()
    reference_uris: set[str] = set()
    for index, asset in enumerate(references, start=1):
        if not isinstance(asset, dict):
            raise ValueError(f"reference asset {index} must be an object")
        if set(asset).difference(REFERENCE_FIELDS):
            raise ValueError(f"reference asset {index} contains unsupported fields")
        asset_id = require_text(asset.get("id"), f"reference asset {index} id", max_units=64)
        if not SAFE_REFERENCE_ID.fullmatch(asset_id):
            raise ValueError("reference asset id must be a lowercase safe identifier")
        title = require_text(asset.get("title"), f"reference asset {index} title", max_units=360)
        if len(title) > 180:
            raise ValueError(f"reference asset {index} title exceeds the length limit")
        source_type = asset.get("source_type")
        if source_type not in {"offline-example", "user-url", "provider-search"}:
            raise ValueError(f"reference asset {index} has an unsupported source_type")
        provider = require_text(asset.get("provider"), f"reference asset {index} provider", max_units=64)
        if not SAFE_PROVIDER_NAME.fullmatch(provider):
            raise ValueError("reference asset provider must be a lowercase safe identifier")
        if asset.get("media_type", "image") not in {"image", "webpage", "document"}:
            raise ValueError(f"reference asset {index} has an unsupported media_type")
        optional_text_limits = {"author": 240, "license_name": 120, "attribution": 500}
        for field, limit in optional_text_limits.items():
            value = asset.get(field)
            if value is not None:
                checked = require_text(value, f"reference asset {index} {field}", max_units=limit * 2)
                if len(checked) > limit:
                    raise ValueError(f"reference asset {index} {field} exceeds the length limit")
        uri_schemes = {"example"} if source_type == "offline-example" else {"http", "https"}
        uri = validate_reference_uri(
            asset.get("uri"),
            f"reference asset {index} uri",
            allowed_schemes=uri_schemes,
        )
        source_url = asset.get("source_url")
        if source_url is not None:
            validate_reference_uri(
                source_url,
                f"reference asset {index} source_url",
                allowed_schemes={"http", "https"},
            )
        license_url = asset.get("license_url")
        if license_url is not None:
            validate_reference_uri(
                license_url,
                f"reference asset {index} license_url",
                allowed_schemes={"http", "https"},
            )
        if source_type == "provider-search":
            if source_url is None:
                raise ValueError("provider-search references require a source_url")
            require_text(
                asset.get("license_name"),
                f"reference asset {index} license_name",
                max_units=240,
            )
        if asset_id in reference_ids or uri in reference_uris:
            raise ValueError("reference asset ids and URIs must be unique")
        reference_ids.add(asset_id)
        reference_uris.add(uri)
    stage_statuses = {stage.get("evidence_status", "illustrative") for stage in stages}
    if plan["evidence_status"] == "measured" and stage_statuses != {"measured"}:
        raise ValueError("overall measured requires every stage to be measured")
    if plan["evidence_status"] == "implemented" and not stage_statuses.issubset({"measured", "implemented"}):
        raise ValueError("overall implemented cannot contain speculative stages")


def multiline(
    x: float,
    y: float,
    value: str,
    size: float,
    max_units: float,
    *,
    max_lines: int = 2,
    line_height: float = 1.25,
    weight: int = 500,
    fill: str | None = None,
    anchor: str = "start",
    theme: WorkflowTheme = DEFAULT_THEME,
) -> str:
    fill = fill or theme.palette["navy"]
    lines = wrap_text(value, max_units, max_lines)
    spans = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * line_height
        spans.append(f'<tspan x="{x:.1f}" dy="{dy:.1f}">{escape(line)}</tspan>')
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size:.1f}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">' + "".join(spans) + "</text>"
    )


def pill(
    x: float,
    y: float,
    w: float,
    label: str,
    fill: str,
    foreground: str,
    *,
    h: float = 34,
    size: float = 15,
    theme: WorkflowTheme = DEFAULT_THEME,
) -> str:
    return rounded(x, y, w, h, fill, "none", h / 2, 0) + text(
        x + w / 2,
        y + h * 0.68,
        label,
        size,
        weight=700,
        fill=foreground,
        anchor="middle",
        theme=theme,
    )


def data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/svg+xml"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def embedded_image(path: Path, x: float, y: float, w: float, h: float) -> str:
    with Image.open(path) as image:
        iw, ih = image.size
    scale = min(w / iw, h / ih)
    rw, rh = iw * scale, ih * scale
    rx, ry = x + (w - rw) / 2, y + (h - rh) / 2
    return (
        f'<image x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" '
        f'preserveAspectRatio="xMidYMid meet" href="{data_uri(path)}"/>'
    )


def fallback_icon(
    kind: str,
    cx: float,
    cy: float,
    accent: str,
    theme: WorkflowTheme = DEFAULT_THEME,
) -> str:
    card = theme.surface["card"]
    pale = theme.light["blue"]
    if kind == "store":
        return (
            f'<ellipse cx="{cx:.1f}" cy="{cy-36:.1f}" rx="58" ry="18" fill="{card}" stroke="{accent}" stroke-width="5"/>'
            f'<rect x="{cx-58:.1f}" y="{cy-36:.1f}" width="116" height="76" fill="{pale}" stroke="{accent}" stroke-width="5"/>'
            f'<ellipse cx="{cx:.1f}" cy="{cy+40:.1f}" rx="58" ry="18" fill="{pale}" stroke="{accent}" stroke-width="5"/>'
        )
    if kind == "decision":
        return f'<path d="M {cx:.1f} {cy-72:.1f} L {cx+72:.1f} {cy:.1f} L {cx:.1f} {cy+72:.1f} L {cx-72:.1f} {cy:.1f} Z" fill="{card}" stroke="{accent}" stroke-width="6"/>'
    if kind == "output":
        return (
            rounded(cx - 60, cy - 72, 120, 144, card, accent, 16, 5)
            + f'<path d="M {cx-34:.1f} {cy+6:.1f} L {cx-6:.1f} {cy+34:.1f} L {cx+42:.1f} {cy-24:.1f}" fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="72" fill="{card}" stroke="{accent}" stroke-width="6"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="24" fill="{accent}"/>'
        f'<path d="M {cx-56:.1f} {cy:.1f} H {cx+56:.1f} M {cx:.1f} {cy-56:.1f} V {cy+56:.1f}" stroke="{accent}" stroke-width="7" stroke-linecap="round"/>'
    )


def ribbon_positions(count: int) -> list[tuple[float, float, float, float]]:
    margin, gap = 52.0, 24.0
    card_w = (WIDTH - 2 * margin - gap * (count - 1)) / count
    return [(margin + index * (card_w + gap), 176.0, card_w, 548.0) for index in range(count)]


def bowtie_positions(count: int) -> list[tuple[float, float, float, float]]:
    if count != 5:
        return ribbon_positions(count)
    return [
        (58, 170, 300, 252),
        (58, 458, 300, 252),
        (690, 190, 420, 510),
        (1442, 170, 300, 252),
        (1442, 458, 300, 252),
    ]


def dual_rail_positions(count: int) -> list[tuple[float, float, float, float]]:
    margin, gap = 74.0, 28.0
    card_w = (WIDTH - 2 * margin - gap * (count - 1)) / count
    return [
        (margin + index * (card_w + gap), 176.0 if index % 2 == 0 else 450.0, card_w, 266.0)
        for index in range(count)
    ]


def get_positions(family: str, count: int) -> list[tuple[float, float, float, float]]:
    if family == "bowtie":
        return bowtie_positions(count)
    if family == "dual-rail":
        return dual_rail_positions(count)
    return ribbon_positions(count)


def approximate_text_width(value: str, size: float) -> float:
    return sum(char_units(char) for char in value) * size / 2


def stage_card(
    stage: dict[str, Any],
    index: int,
    box: tuple[float, float, float, float],
    asset_dir: Path,
    *,
    theme: WorkflowTheme = DEFAULT_THEME,
    layout_preset: str = "standard",
) -> tuple[str, dict[str, Any]]:
    x, y, w, h = box
    accent_name = stage.get("accent", "blue")
    accent = theme.palette.get(accent_name, theme.palette["blue"])
    compact = h < 320
    presentation = layout_preset == "presentation-spacious"
    parts = [
        f'<g filter="url(#card-shadow)">{rounded(x, y, w, h, theme.surface["card"], theme.surface["card_border"], 26, 1.4)}</g>'
    ]
    parts.append(rounded(x, y, w, 9, accent, "none", 5, 0))
    parts.append(
        pill(x + 18, y + 20, 48, f"{index:02d}", accent, theme.surface["card"], h=34, size=15, theme=theme)
    )
    stage_status = stage.get("evidence_status", "illustrative")
    status = STATUS_TEXT.get(stage_status, "示意")
    status_color_name = STATUS_COLOR.get(stage_status, "gray")
    status_w = max(68, 24 + sum(char_units(char) for char in status) * 7)
    parts.append(
        pill(
            x + w - status_w - 16,
            y + 20,
            status_w,
            status,
            theme.light[status_color_name],
            theme.palette[status_color_name],
            h=34,
            size=14,
            theme=theme,
        )
    )

    if presentation:
        icon_h = 82 if compact else 190
        icon_y = y + 60 if compact else y + 70
    else:
        icon_h = 112 if compact else 218
        icon_y = y + 62 if compact else y + 78
    icon_path = asset_dir / f'{stage.get("asset_key", "process")}.png'
    if icon_path.exists():
        parts.append(embedded_image(icon_path, x + 22, icon_y, w - 44, icon_h))
    else:
        icon_cx, icon_cy = x + w / 2, icon_y + icon_h / 2
        icon_svg = fallback_icon(stage.get("asset_key", "process"), icon_cx, icon_cy, accent, theme)
        icon_scale = min(1.0, icon_h / 154.0)
        parts.append(
            f'<g transform="translate({icon_cx:.1f} {icon_cy:.1f}) scale({icon_scale:.3f}) '
            f'translate({-icon_cx:.1f} {-icon_cy:.1f})">{icon_svg}</g>'
        )

    if presentation and compact:
        text_y = y + 176
        title_size, subtitle_size, body_size = 27.5, 18.75, 20.0
        title_line_height = 1.05
        title_max_lines = 2
        subtitle_y = min(y + 239, y + h - 21)
        subtitle_max_lines = 1
    elif presentation:
        text_y = y + 295
        title_size, subtitle_size, body_size = 31.25, 21.25, 20.0
        title_line_height = 1.08
        title_max_lines = 2
        subtitle_y = 0.0
        subtitle_max_lines = 2
    elif compact:
        text_y = y + 198
        title_size, subtitle_size, body_size = 22.0, 15.0, 16.0
        title_line_height = 1.0
        title_max_lines = 1
        subtitle_y = text_y + 32
        subtitle_max_lines = 2
    else:
        text_y = y + 338
        title_size, subtitle_size, body_size = 25.0, 17.0, 16.0
        title_line_height = 1.0
        title_max_lines = 1
        subtitle_y = text_y + 32
        subtitle_max_lines = 2

    title_units = max(1.0, sum(char_units(char) for char in stage["title"]))
    if presentation:
        title_wrap_units = max(8.0, 2 * (w - 44) / title_size)
        title_lines = wrap_text(stage["title"], title_wrap_units, title_max_lines)
        parts.append(
            multiline(
                x + 22,
                text_y,
                stage["title"],
                title_size,
                title_wrap_units,
                max_lines=title_max_lines,
                line_height=title_line_height,
                weight=800,
                theme=theme,
            )
        )
    else:
        title_size = min(title_size, max(16, 2 * (w - 44) / title_units))
        title_lines = [stage["title"]]
        parts.append(text(x + 22, text_y, stage["title"], title_size, weight=800, theme=theme))
    title_last_y = text_y + (len(title_lines) - 1) * title_size * title_line_height
    if presentation and not compact:
        subtitle_y = title_last_y + 40
    subtitle_wrap_units = max(12, (w - 44) / subtitle_size * 1.72)
    subtitle_lines = wrap_text(stage.get("subtitle", ""), subtitle_wrap_units, subtitle_max_lines)
    parts.append(
        multiline(
            x + 22,
            subtitle_y,
            stage.get("subtitle", ""),
            subtitle_size,
            subtitle_wrap_units,
            max_lines=subtitle_max_lines,
            fill=theme.palette["gray"],
            theme=theme,
        )
    )
    subtitle_last_y = subtitle_y + (len(subtitle_lines) - 1) * subtitle_size * 1.25

    body_bottoms: list[float] = []
    body_horizontal_ok = True
    if not compact:
        body_y = max(y + (442 if presentation else 439), subtitle_last_y + (50 if presentation else 48))
        body_limit = 2 if presentation else 3
        body_step = 45 if presentation else 36
        for line_index, line in enumerate(stage.get("body", [])[:body_limit]):
            cy = body_y + line_index * body_step
            parts.append(f'<circle cx="{x+29:.1f}" cy="{cy-5:.1f}" r="4.5" fill="{accent}"/>')
            body_wrap_units = max(
                12,
                2 * (w - 66) / body_size if presentation else (w - 66) / body_size * 1.55,
            )
            body_lines = wrap_text(line, body_wrap_units, 1)
            body_horizontal_ok = body_horizontal_ok and all(
                approximate_text_width(body_line, body_size) <= w - 66 + 1 for body_line in body_lines
            )
            parts.append(
                multiline(
                    x + 43,
                    cy,
                    line,
                    body_size,
                    body_wrap_units,
                    max_lines=1,
                    fill=theme.palette["navy"],
                    theme=theme,
                )
            )
            body_bottoms.append(cy + body_size * 0.4)

    horizontal_ok = all(
        approximate_text_width(line, title_size) <= w - 44 + 1 for line in title_lines
    ) and all(approximate_text_width(line, subtitle_size) <= w - 44 + 1 for line in subtitle_lines)
    horizontal_ok = horizontal_ok and body_horizontal_ok
    block_bottoms = [title_last_y + title_size * 0.4, subtitle_last_y + subtitle_size * 0.4, *body_bottoms]
    vertical_ok = max(block_bottoms) <= y + h - 8
    qa = {
        "stage": index,
        "compact": compact,
        "title_lines": len(title_lines),
        "subtitle_lines": len(subtitle_lines),
        "body_lines": min(len(stage.get("body", [])), 2 if presentation else 3) if not compact else 0,
        "title_font_size": round(title_size, 2),
        "subtitle_font_size": round(subtitle_size, 2),
        "body_font_size": round(body_size, 2) if not compact and stage.get("body") else None,
        "horizontal_ok": horizontal_ok,
        "vertical_ok": vertical_ok,
    }
    return "".join(parts), qa


def connector(
    source: tuple[float, float, float, float],
    target: tuple[float, float, float, float],
    accent_name: str,
    theme: WorkflowTheme = DEFAULT_THEME,
) -> str:
    accent = theme.palette.get(accent_name, theme.palette["blue"])
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    x1, y1 = sx + sw, sy + sh / 2
    x2, y2 = tx, ty + th / 2
    if x2 <= x1:
        x1, y1 = sx + sw / 2, sy + sh
        x2, y2 = tx + tw / 2, ty
    bend = max(34.0, abs(x2 - x1) * 0.34)
    return (
        f'<path d="M {x1:.1f} {y1:.1f} C {x1+bend:.1f} {y1:.1f}, {x2-bend:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}" '
        f'fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" marker-end="url(#arrow-{accent_name})"/>'
    )


def render(plan_path: Path, asset_dir: Path, output_dir: Path, output_name: str) -> dict[str, str]:
    if not SAFE_OUTPUT_NAME.fullmatch(output_name):
        raise ValueError("output name must be a safe filename without path separators")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("plan root must be an object")
    validate_plan(plan)
    theme = load_theme(plan.get("theme", "academic-audit"))
    layout_preset = plan.get("layout_preset", "standard")
    presentation = layout_preset == "presentation-spacious"
    stages = plan.get("stages", [])
    positions = get_positions(plan.get("layout_family", "ribbon"), len(stages))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" data-theme="{theme.name}" data-layout-preset="{layout_preset}">',
        "<defs>",
        f'<linearGradient id="page-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{theme.surface["background_start"]}"/><stop offset=".55" stop-color="{theme.surface["background_mid"]}"/><stop offset="1" stop-color="{theme.surface["background_end"]}"/></linearGradient>',
        f'<filter id="card-shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="8" stdDeviation="11" flood-color="{theme.surface["shadow"]}" flood-opacity=".13"/></filter>',
        *[
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{theme.palette[name]}"/></marker>'
            for name in ("navy", "blue", "teal", "orange", "violet")
        ],
        "</defs>",
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#page-bg)"/>',
        f'<circle cx="1550" cy="120" r="95" fill="{theme.surface["decoration_primary"]}" opacity=".42"/>',
        f'<circle cx="150" cy="850" r="110" fill="{theme.surface["decoration_secondary"]}" opacity=".56"/>',
        text(
            54,
            62,
            plan["title"],
            min(39 if presentation else 34, max(27 if presentation else 24, 2860 / max(1, sum(char_units(c) for c in plan["title"])))),
            weight=850,
            theme=theme,
        ),
        multiline(
            54,
            103,
            plan["takeaway"],
            23 if presentation else 20,
            64 if presentation else 70,
            max_lines=2,
            fill=theme.palette["gray"],
            theme=theme,
        ),
    ]

    overall_status = plan.get("evidence_status", "illustrative")
    status_label = plan.get("status_label", STATUS_TEXT.get(overall_status, "状态未标注"))
    status_color_name = STATUS_COLOR.get(overall_status, "gray")
    top_status_units = max(1.0, sum(char_units(char) for char in status_label))
    top_status_size = min(18, max(13, 2 * (326 - 30) / top_status_units))
    parts.append(
        pill(
            1420,
            36,
            326,
            status_label,
            theme.light[status_color_name],
            theme.palette[status_color_name],
            h=44,
            size=top_status_size,
            theme=theme,
        )
    )

    family = plan.get("layout_family", "ribbon")
    if family == "ribbon":
        rail_y = positions[0][1] + positions[0][3] / 2
        parts.append(f'<path d="M 70 {rail_y:.1f} H 1730" stroke="{theme.surface["rail"]}" stroke-width="22" stroke-linecap="round" opacity=".62"/>')
    elif family == "dual-rail":
        parts.append(f'<path d="M 80 436 H 1720" stroke="{theme.surface["rail"]}" stroke-width="18" stroke-linecap="round" opacity=".68"/>')

    for index in range(len(positions) - 1):
        source_accent = stages[index].get("accent", "blue")
        parts.append(connector(positions[index], positions[index + 1], source_accent, theme))
    stage_qa: list[dict[str, Any]] = []
    for index, (stage, box) in enumerate(zip(stages, positions), start=1):
        parts.append(f'<g id="stage-{index:02d}" data-asset-key="{stage.get("asset_key", "process")}">')
        card_svg, card_qa = stage_card(
            stage,
            index,
            box,
            asset_dir,
            theme=theme,
            layout_preset=layout_preset,
        )
        parts.append(card_svg)
        stage_qa.append(card_qa)
        parts.append("</g>")

    gate_y, gate_h = 766, 154
    parts.append(
        f'<g filter="url(#card-shadow)">{rounded(52, gate_y, WIDTH - 104, gate_h, theme.surface["card"], theme.surface["card_border"], 24, 1.3)}</g>'
    )
    parts.append(text(80, gate_y + 40, "质量门禁", 26.25 if presentation else 21, weight=800, theme=theme))
    parts.append(
        text(
            80,
            gate_y + 75,
            "每一步可检查、可替换、可追溯",
            20 if presentation else 16,
            fill=theme.palette["gray"],
            theme=theme,
        )
    )
    gates = plan.get("gates", [])
    gx = 438.0
    available = WIDTH - gx - 78
    gap = 13.0
    raw = [
        max(150.0, 52.0 + sum(char_units(char) for char in label) * (12.5 if presentation else 10.5))
        for label in gates
    ]
    scale = min(1.0, (available - gap * max(0, len(raw) - 1)) / max(1.0, sum(raw)))
    colors = ["blue", "teal", "violet", "orange", "navy"]
    gate_font_sizes: list[float] = []
    gate_horizontal_ok = True
    for index, (label, raw_w) in enumerate(zip(gates, raw)):
        color_name = colors[index % len(colors)]
        w = raw_w * scale
        label_units = max(1.0, sum(char_units(char) for char in label))
        label_size = min(21.25 if presentation else 17, max(15 if presentation else 12, 2 * (w - 22) / label_units))
        gate_font_sizes.append(label_size)
        gate_horizontal_ok = gate_horizontal_ok and approximate_text_width(label, label_size) <= w - 22 + 1
        parts.append(
            pill(
                gx,
                gate_y + (50 if presentation else 52),
                w,
                label,
                theme.light[color_name],
                theme.palette[color_name],
                h=50 if presentation else 46,
                size=label_size,
                theme=theme,
            )
        )
        gx += w + gap

    warnings = plan.get("warnings", [])
    if warnings:
        suffix = f"（另 {len(warnings) - 1} 条见 Manifest）" if len(warnings) > 1 else ""
        parts.append(
            multiline(
                80,
                gate_y + 130,
                "提示：" + warnings[0] + suffix,
                14 if presentation else 13,
                38,
                max_lines=2,
                fill=theme.palette["orange"],
                theme=theme,
            )
        )

    parts.append(
        multiline(
            54,
            958,
            plan.get("caption", ""),
            14,
            145,
            max_lines=2,
            fill=theme.palette["gray"],
            theme=theme,
        )
    )
    if family != "ribbon":
        parts.append(
            text(
                1746,
                941,
                "紧凑候选仅显示节点摘要；正文保留在 Manifest",
                12,
                fill=theme.palette["gray"],
                anchor="end",
                theme=theme,
            )
        )
    parts.append(
        text(
            1746,
            964,
            "FigureFlow · editable SVG / PDF / PNG",
            14,
            fill=theme.palette["gray"],
            anchor="end",
            theme=theme,
        )
    )
    parts.append("</svg>")
    svg = "\n".join(parts)

    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / f"{output_name}.svg"
    pdf_path = output_dir / f"{output_name}.pdf"
    png_path = output_dir / f"{output_name}.png"
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=str(pdf_path))
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), output_width=2700, output_height=1500)
    manifest_path = output_dir / f"{output_name}_manifest.json"
    card_bounds_ok = all(
        x >= 0 and y >= 0 and x + width <= WIDTH and y + height <= HEIGHT
        for x, y, width, height in positions
    )
    body_sizes = [item["body_font_size"] for item in stage_qa if item["body_font_size"] is not None]
    presentation_scale_ok = not presentation or (
        min(item["title_font_size"] for item in stage_qa) >= 27.5
        and min(item["subtitle_font_size"] for item in stage_qa) >= 18.75
        and (not body_sizes or min(body_sizes) >= 20.0)
        and (not gate_font_sizes or min(gate_font_sizes) >= 21.25)
    )
    layout_qa = {
        "ok": card_bounds_ok
        and gate_horizontal_ok
        and presentation_scale_ok
        and all(item["horizontal_ok"] and item["vertical_ok"] for item in stage_qa),
        "layout_preset": layout_preset,
        "card_bounds_ok": card_bounds_ok,
        "gate_horizontal_ok": gate_horizontal_ok,
        "presentation_scale_ok": presentation_scale_ok,
        "minimum_stage_title_size": min(item["title_font_size"] for item in stage_qa),
        "minimum_stage_subtitle_size": min(item["subtitle_font_size"] for item in stage_qa),
        "minimum_stage_body_size": min(body_sizes) if body_sizes else None,
        "minimum_gate_size": round(min(gate_font_sizes), 2) if gate_font_sizes else None,
        "stages": stage_qa,
    }
    manifest = {
        "schema_version": 2,
        "evidence_status": plan.get("evidence_status"),
        "layout_family": family,
        "layout_preset": layout_preset,
        "theme": theme.name,
        "theme_tokens": theme.source_path.name,
        "theme_tokens_sha256": sha256(theme.source_path),
        "font_family": FONT,
        "layout_qa": layout_qa,
        "plan": plan_path.name,
        "plan_sha256": sha256(plan_path),
        "reference_assets": plan.get("reference_assets", []),
        "assets": [
            {"file": f"{stage.get('asset_key')}.png", "sha256": sha256(asset_dir / f"{stage.get('asset_key')}.png")}
            for stage in stages
            if (asset_dir / f"{stage.get('asset_key')}.png").exists()
        ],
        "outputs": {path.suffix.removeprefix("."): path.name for path in (svg_path, pdf_path, png_path)},
        "output_sha256": {path.name: sha256(path) for path in (svg_path, pdf_path, png_path)},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"svg": str(svg_path), "pdf": str(pdf_path), "png": str(png_path), "manifest": str(manifest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-name", default="figureflow_workflow")
    args = parser.parse_args()
    result = render(args.plan.resolve(), args.asset_dir.resolve(), args.output_dir.resolve(), args.output_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
