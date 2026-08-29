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
from pathlib import Path
from typing import Any
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
SAFE_ASSET_KEYS = {
    "layout_planner",
    "icon_factory",
    "chroma_matte",
    "vector_typeset",
    "qa_export",
    "data",
    "process",
    "decision",
    "store",
    "output",
}
SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
PALETTE = {
    "navy": "#142B4A",
    "blue": "#2A6FBB",
    "teal": "#16827A",
    "orange": "#E58B2A",
    "violet": "#7A5195",
    "red": "#B84A3A",
    "gray": "#647180",
    "line": "#C8D5E2",
    "paper": "#F6F8FC",
    "white": "#FFFFFF",
}
LIGHT = {
    "navy": "#E8EEF6",
    "blue": "#E8F2FC",
    "teal": "#E6F5F2",
    "orange": "#FFF1DF",
    "violet": "#F2EAF7",
    "red": "#FBE9E6",
    "gray": "#EEF1F4",
}
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


def text(x: float, y: float, value: str, size: float, *, weight: int = 500, fill: str = PALETTE["navy"], anchor: str = "start", opacity: float = 1.0) -> str:
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


def validate_plan(plan: dict[str, Any]) -> None:
    """Validate the standalone CLI contract without importing the demo package."""
    require_text(plan.get("title"), "title", max_units=60)
    require_text(plan.get("takeaway"), "takeaway", max_units=180)
    require_text(plan.get("status_label"), "status_label", max_units=30)
    require_text(plan.get("caption"), "caption", max_units=360)
    if plan.get("layout_family", "ribbon") not in ALLOWED_LAYOUTS:
        raise ValueError("unsupported layout family")
    if plan.get("theme", "academic-audit") != "academic-audit":
        raise ValueError("render_workflow currently supports only academic-audit")
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
        require_text(stage.get("subtitle"), f"stage {index} subtitle", max_units=44)
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
        for body_index, line in enumerate(body, start=1):
            require_text(line, f"stage {index} body {body_index}", max_units=84)
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
    stage_statuses = {stage.get("evidence_status", "illustrative") for stage in stages}
    if plan["evidence_status"] == "measured" and stage_statuses != {"measured"}:
        raise ValueError("overall measured requires every stage to be measured")
    if plan["evidence_status"] == "implemented" and not stage_statuses.issubset({"measured", "implemented"}):
        raise ValueError("overall implemented cannot contain speculative stages")


def multiline(x: float, y: float, value: str, size: float, max_units: float, *, max_lines: int = 2, line_height: float = 1.25, weight: int = 500, fill: str = PALETTE["navy"], anchor: str = "start") -> str:
    lines = wrap_text(value, max_units, max_lines)
    spans = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * line_height
        spans.append(f'<tspan x="{x:.1f}" dy="{dy:.1f}">{escape(line)}</tspan>')
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size:.1f}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">' + "".join(spans) + "</text>"
    )


def pill(x: float, y: float, w: float, label: str, fill: str, foreground: str, *, h: float = 34, size: float = 15) -> str:
    return rounded(x, y, w, h, fill, "none", h / 2, 0) + text(x + w / 2, y + h * 0.68, label, size, weight=700, fill=foreground, anchor="middle")


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


def fallback_icon(kind: str, cx: float, cy: float, accent: str) -> str:
    if kind == "store":
        return (
            f'<ellipse cx="{cx:.1f}" cy="{cy-36:.1f}" rx="58" ry="18" fill="#FFFFFF" stroke="{accent}" stroke-width="5"/>'
            f'<rect x="{cx-58:.1f}" y="{cy-36:.1f}" width="116" height="76" fill="{LIGHT["blue"]}" stroke="{accent}" stroke-width="5"/>'
            f'<ellipse cx="{cx:.1f}" cy="{cy+40:.1f}" rx="58" ry="18" fill="{LIGHT["blue"]}" stroke="{accent}" stroke-width="5"/>'
        )
    if kind == "decision":
        return f'<path d="M {cx:.1f} {cy-72:.1f} L {cx+72:.1f} {cy:.1f} L {cx:.1f} {cy+72:.1f} L {cx-72:.1f} {cy:.1f} Z" fill="#FFFFFF" stroke="{accent}" stroke-width="6"/>'
    if kind == "output":
        return (
            rounded(cx - 60, cy - 72, 120, 144, "#FFFFFF", accent, 16, 5)
            + f'<path d="M {cx-34:.1f} {cy+6:.1f} L {cx-6:.1f} {cy+34:.1f} L {cx+42:.1f} {cy-24:.1f}" fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="72" fill="#FFFFFF" stroke="{accent}" stroke-width="6"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="24" fill="{accent}"/>'
        f'<path d="M {cx-56:.1f} {cy:.1f} H {cx+56:.1f} M {cx:.1f} {cy-56:.1f} V {cx+56:.1f}" stroke="{accent}" stroke-width="7" stroke-linecap="round"/>'
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


def stage_card(stage: dict[str, Any], index: int, box: tuple[float, float, float, float], asset_dir: Path) -> str:
    x, y, w, h = box
    accent_name = stage.get("accent", "blue")
    accent = PALETTE.get(accent_name, PALETTE["blue"])
    light = LIGHT.get(accent_name, LIGHT["blue"])
    compact = h < 320
    parts = [f'<g filter="url(#card-shadow)">{rounded(x, y, w, h, "#FFFFFF", "#D9E3EE", 26, 1.4)}</g>']
    parts.append(rounded(x, y, w, 9, accent, "none", 5, 0))
    parts.append(pill(x + 18, y + 20, 48, f"{index:02d}", accent, "#FFFFFF", h=34, size=15))
    stage_status = stage.get("evidence_status", "illustrative")
    status = STATUS_TEXT.get(stage_status, "示意")
    status_color_name = STATUS_COLOR.get(stage_status, "gray")
    status_w = max(68, 24 + sum(char_units(char) for char in status) * 7)
    parts.append(pill(x + w - status_w - 16, y + 20, status_w, status, LIGHT[status_color_name], PALETTE[status_color_name], h=34, size=14))

    icon_h = 112 if compact else 218
    icon_y = y + 62 if compact else y + 78
    icon_path = asset_dir / f'{stage.get("asset_key", "process")}.png'
    if icon_path.exists():
        parts.append(embedded_image(icon_path, x + 22, icon_y, w - 44, icon_h))
    else:
        parts.append(fallback_icon(stage.get("asset_key", "process"), x + w / 2, icon_y + icon_h / 2, accent))

    if compact:
        text_y = y + 198
        title_size, subtitle_size = 22, 15
    else:
        text_y = y + 338
        title_size, subtitle_size = 25, 17
    title_units = max(1.0, sum(char_units(char) for char in stage["title"]))
    title_size = min(title_size, max(16, 2 * (w - 44) / title_units))
    parts.append(text(x + 22, text_y, stage["title"], title_size, weight=800))
    parts.append(multiline(x + 22, text_y + 32, stage.get("subtitle", ""), subtitle_size, max(12, (w - 44) / subtitle_size * 1.72), max_lines=2, fill=PALETTE["gray"]))

    if not compact:
        body_y = text_y + 101
        for line_index, line in enumerate(stage.get("body", [])[:3]):
            cy = body_y + line_index * 36
            parts.append(f'<circle cx="{x+29:.1f}" cy="{cy-5:.1f}" r="4.5" fill="{accent}"/>')
            parts.append(multiline(x + 43, cy, line, 16, max(12, (w - 66) / 16 * 1.55), max_lines=1, fill=PALETTE["navy"]))
    return "".join(parts)


def connector(source: tuple[float, float, float, float], target: tuple[float, float, float, float], accent_name: str) -> str:
    accent = PALETTE.get(accent_name, PALETTE["blue"])
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
    stages = plan.get("stages", [])
    positions = get_positions(plan.get("layout_family", "ribbon"), len(stages))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        "<defs>",
        '<linearGradient id="page-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F8FBFE"/><stop offset=".55" stop-color="#F4F8FC"/><stop offset="1" stop-color="#EEF4FA"/></linearGradient>',
        '<filter id="card-shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="8" stdDeviation="11" flood-color="#425C78" flood-opacity=".13"/></filter>',
        *[
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{PALETTE[name]}"/></marker>'
            for name in ("navy", "blue", "teal", "orange", "violet")
        ],
        "</defs>",
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#page-bg)"/>',
        '<circle cx="1660" cy="40" r="240" fill="#DCEAF7" opacity=".42"/>',
        '<circle cx="95" cy="940" r="260" fill="#E4F4F1" opacity=".56"/>',
        text(54, 62, plan["title"], min(34, max(24, 2560 / max(1, sum(char_units(c) for c in plan["title"])))), weight=850),
        multiline(54, 103, plan["takeaway"], 20, 70, max_lines=2, fill=PALETTE["gray"]),
    ]

    overall_status = plan.get("evidence_status", "illustrative")
    status_label = plan.get("status_label", STATUS_TEXT.get(overall_status, "状态未标注"))
    status_color_name = STATUS_COLOR.get(overall_status, "gray")
    top_status_units = max(1.0, sum(char_units(char) for char in status_label))
    top_status_size = min(18, max(13, 2 * (326 - 30) / top_status_units))
    parts.append(pill(1420, 36, 326, status_label, LIGHT[status_color_name], PALETTE[status_color_name], h=44, size=top_status_size))

    family = plan.get("layout_family", "ribbon")
    if family == "ribbon":
        rail_y = positions[0][1] + positions[0][3] / 2
        parts.append(f'<path d="M 70 {rail_y:.1f} H 1730" stroke="#D7E4F0" stroke-width="22" stroke-linecap="round" opacity=".62"/>')
    elif family == "dual-rail":
        parts.append('<path d="M 80 436 H 1720" stroke="#D7E4F0" stroke-width="18" stroke-linecap="round" opacity=".68"/>')

    for index in range(len(positions) - 1):
        source_accent = stages[index].get("accent", "blue")
        parts.append(connector(positions[index], positions[index + 1], source_accent))
    for index, (stage, box) in enumerate(zip(stages, positions), start=1):
        parts.append(f'<g id="stage-{index:02d}" data-asset-key="{stage.get("asset_key", "process")}">')
        parts.append(stage_card(stage, index, box, asset_dir))
        parts.append("</g>")

    gate_y, gate_h = 766, 154
    parts.append(f'<g filter="url(#card-shadow)">{rounded(52, gate_y, WIDTH - 104, gate_h, "#FFFFFF", "#D9E3EE", 24, 1.3)}</g>')
    parts.append(text(80, gate_y + 40, "质量门禁", 21, weight=800))
    parts.append(text(80, gate_y + 71, "每一步可检查、可替换、可追溯", 16, fill=PALETTE["gray"]))
    gates = plan.get("gates", [])
    gx = 438.0
    available = WIDTH - gx - 78
    gap = 13.0
    raw = [max(150.0, 52.0 + sum(char_units(char) for char in label) * 10.5) for label in gates]
    scale = min(1.0, (available - gap * max(0, len(raw) - 1)) / max(1.0, sum(raw)))
    colors = ["blue", "teal", "violet", "orange", "navy"]
    for index, (label, raw_w) in enumerate(zip(gates, raw)):
        color_name = colors[index % len(colors)]
        w = raw_w * scale
        label_units = max(1.0, sum(char_units(char) for char in label))
        label_size = min(17, max(12, 2 * (w - 22) / label_units))
        parts.append(pill(gx, gate_y + 52, w, label, LIGHT[color_name], PALETTE[color_name], h=46, size=label_size))
        gx += w + gap

    warnings = plan.get("warnings", [])
    if warnings:
        suffix = f"（另 {len(warnings) - 1} 条见 Manifest）" if len(warnings) > 1 else ""
        parts.append(multiline(80, gate_y + 126, "提示：" + warnings[0] + suffix, 13, 38, max_lines=2, fill=PALETTE["orange"]))

    parts.append(multiline(54, 958, plan.get("caption", ""), 14, 145, max_lines=2, fill=PALETTE["gray"]))
    if family != "ribbon":
        parts.append(text(1746, 941, "紧凑候选仅显示节点摘要；正文保留在 Manifest", 12, fill=PALETTE["gray"], anchor="end"))
    parts.append(text(1746, 964, "FigureFlow · editable SVG / PDF / PNG", 14, fill=PALETTE["gray"], anchor="end"))
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
    manifest = {
        "schema_version": 1,
        "evidence_status": plan.get("evidence_status"),
        "layout_family": family,
        "font_family": FONT,
        "plan": plan_path.name,
        "plan_sha256": sha256(plan_path),
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
