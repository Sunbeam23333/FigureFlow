#!/usr/bin/env python3
"""Render a deterministic SVG/PDF overview figure from a YAML specification."""

from __future__ import annotations

import argparse
import base64
import io
import re
import textwrap
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from visual_common import PALETTE, THEME, color, configure_matplotlib, load_yaml, status_colors, write_artifact_manifest

import cairosvg
import matplotlib.pyplot as plt


DISPLAY_FONT = ",".join(
    [*(f"'{name}'" for name in THEME["typography"]["display"][:-1]), THEME["typography"]["display"][-1]]
)
_MATH_CACHE: dict[tuple[str, int, str], tuple[str, float]] = {}


def rounded(x, y, w, h, fill, stroke=None, radius=18, sw=1.5) -> str:
    stroke = stroke or PALETTE["line"]
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
        f'rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
    )


def text(x, y, value, size=22, weight=400, fill=None, anchor="start", opacity=1) -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="{DISPLAY_FONT}" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill or PALETTE["navy"]}" '
        f'text-anchor="{anchor}" opacity="{opacity}">{escape(str(value))}</text>'
    )


def wrapped_text(
    x: float,
    y: float,
    value: str,
    max_width: float,
    *,
    size: float = 22,
    weight: int = 400,
    fill: str | None = None,
    max_lines: int = 2,
    line_height: float = 1.16,
) -> str:
    """Render deterministic SVG text wrapping without browser-dependent layout."""
    max_chars = max(8, int(max_width / (size * 0.54)))
    lines = textwrap.wrap(str(value), width=max_chars, break_long_words=False) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + "..."
    spans = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * line_height
        spans.append(f'<tspan x="{x:.2f}" dy="{dy:.2f}">{escape(line)}</tspan>')
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="{DISPLAY_FONT}" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill or PALETTE["navy"]}">' 
        + "".join(spans)
        + "</text>"
    )


def pill(x, y, w, label, fill, foreground=None, height=34, size=15) -> str:
    return rounded(x, y, w, height, fill, stroke="none", radius=height / 2, sw=0) + text(
        x + w / 2,
        y + height * 0.68,
        label,
        size,
        700,
        foreground or PALETTE["navy"],
        "middle",
    )


def math_svg_uri(expression: str, fontsize: int = 22, formula_color: str | None = None) -> tuple[str, float]:
    formula_color = formula_color or PALETTE["navy"]
    key = (expression, fontsize, formula_color)
    if key in _MATH_CACHE:
        return _MATH_CACHE[key]
    configure_matplotlib(display=False)
    with plt.rc_context({"svg.fonttype": "path", "mathtext.fontset": "stixsans"}):
        fig = plt.figure(figsize=(8, 1.3), facecolor="none")
        fig.text(0.01, 0.18, f"${expression}$", fontsize=fontsize, color=formula_color)
        stream = io.StringIO()
        fig.savefig(stream, format="svg", bbox_inches="tight", pad_inches=0, transparent=True)
        plt.close(fig)
    payload = stream.getvalue()
    match = re.search(r'viewBox="([^"]+)"', payload)
    if not match:
        raise RuntimeError("math SVG is missing a viewBox")
    _, _, width, height = map(float, match.group(1).split())
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    result = (f"data:image/svg+xml;base64,{encoded}", width / height)
    _MATH_CACHE[key] = result
    return result


def formula(x: float, center_y: float, width: float, expression: str, fontsize: int = 22) -> str:
    source, aspect = math_svg_uri(expression, fontsize)
    height = width / aspect
    return (
        f'<image x="{x:.2f}" y="{center_y - height / 2:.2f}" width="{width:.2f}" '
        f'height="{height:.2f}" preserveAspectRatio="xMidYMid meet" href="{source}"/>'
    )


def arrow(x1, y1, x2, y2, arrow_color, *, bend=0, dashed=False, width=3.0) -> str:
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    marker = arrow_color[1:]
    return (
        f'<path d="M {x1:.2f} {y1:.2f} C {x1 + 22:.2f} {y1 + bend:.2f}, '
        f'{x2 - 22:.2f} {y2 - bend:.2f}, {x2:.2f} {y2:.2f}" fill="none" '
        f'stroke="{arrow_color}" stroke-width="{width}" stroke-linecap="round"{dash} '
        f'marker-end="url(#arrow-{marker})"/>'
    )


def icon_data(cx: float, cy: float, accent: str) -> str:
    return "".join(
        [
            f'<ellipse cx="{cx - 70}" cy="{cy - 42}" rx="42" ry="13" fill="#FFFFFF" stroke="{accent}" stroke-width="3"/>',
            f'<rect x="{cx - 112}" y="{cy - 42}" width="84" height="74" fill="{PALETTE["light_blue"]}" stroke="{accent}" stroke-width="3"/>',
            f'<ellipse cx="{cx - 70}" cy="{cy + 32}" rx="42" ry="13" fill="{PALETTE["light_blue"]}" stroke="{accent}" stroke-width="3"/>',
            f'<path d="M {cx - 20} {cy - 5} L {cx + 27} {cy - 5}" stroke="{accent}" stroke-width="5" marker-end="url(#arrow-{accent[1:]})"/>',
            rounded(cx + 36, cy - 67, 90, 124, "#FFFFFF", accent, 12, 3),
            f'<line x1="{cx + 54}" y1="{cy - 34}" x2="{cx + 108}" y2="{cy - 34}" stroke="{PALETTE["line"]}" stroke-width="5"/>',
            f'<line x1="{cx + 54}" y1="{cy - 7}" x2="{cx + 108}" y2="{cy - 7}" stroke="{PALETTE["line"]}" stroke-width="5"/>',
            f'<line x1="{cx + 54}" y1="{cy + 20}" x2="{cx + 92}" y2="{cy + 20}" stroke="{PALETTE["line"]}" stroke-width="5"/>',
        ]
    )


def icon_probe(cx: float, cy: float, accent: str) -> str:
    nodes = []
    for dx, dy in [(-42, -34), (0, -52), (42, -30), (-32, 18), (20, 26)]:
        nodes.append(f'<circle cx="{cx + dx}" cy="{cy + dy}" r="9" fill="{PALETTE["light_teal"]}" stroke="{accent}" stroke-width="3"/>')
    links = [
        f'<line x1="{cx - 42}" y1="{cy - 34}" x2="{cx}" y2="{cy - 52}" stroke="{PALETTE["line"]}" stroke-width="3"/>',
        f'<line x1="{cx}" y1="{cy - 52}" x2="{cx + 42}" y2="{cy - 30}" stroke="{PALETTE["line"]}" stroke-width="3"/>',
        f'<line x1="{cx - 42}" y1="{cy - 34}" x2="{cx - 32}" y2="{cy + 18}" stroke="{PALETTE["line"]}" stroke-width="3"/>',
        f'<line x1="{cx - 32}" y1="{cy + 18}" x2="{cx + 20}" y2="{cy + 26}" stroke="{PALETTE["line"]}" stroke-width="3"/>',
    ]
    return "".join(
        [
            rounded(cx - 92, cy - 83, 148, 132, "#FFFFFF", accent, 18, 3),
            *links,
            *nodes,
            f'<circle cx="{cx + 58}" cy="{cy + 20}" r="43" fill="none" stroke="{accent}" stroke-width="8"/>',
            f'<line x1="{cx + 88}" y1="{cy + 51}" x2="{cx + 126}" y2="{cy + 90}" stroke="{accent}" stroke-width="11" stroke-linecap="round"/>',
        ]
    )


def icon_curve(cx: float, cy: float, accent: str) -> str:
    secondary = PALETTE["orange"]
    return "".join(
        [
            f'<line x1="{cx - 112}" y1="{cy + 65}" x2="{cx + 112}" y2="{cy + 65}" stroke="{PALETTE["line"]}" stroke-width="3"/>',
            f'<line x1="{cx - 112}" y1="{cy - 72}" x2="{cx - 112}" y2="{cy + 65}" stroke="{PALETTE["line"]}" stroke-width="3"/>',
            f'<path d="M {cx - 108} {cy + 34} C {cx - 60} {cy + 20}, {cx - 20} {cy - 65}, {cx + 25} {cy - 38} C {cx + 60} {cy - 17}, {cx + 78} {cy + 25}, {cx + 108} {cy + 37}" fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round"/>',
            f'<path d="M {cx - 108} {cy + 50} C {cx - 65} {cy + 43}, {cx - 18} {cy - 28}, {cx + 28} {cy - 12} C {cx + 66} {cy + 1}, {cx + 82} {cy + 35}, {cx + 108} {cy + 45}" fill="none" stroke="{secondary}" stroke-width="7" stroke-linecap="round"/>',
        ]
    )


def icon_stress(cx: float, cy: float, accent: str) -> str:
    parts = [
        f'<path d="M {cx - 112} {cy + 48} C {cx - 66} {cy + 20}, {cx - 10} {cy + 12}, {cx + 24} {cy - 12} C {cx + 68} {cy - 42}, {cx + 80} {cy - 72}, {cx + 112} {cy - 92}" fill="none" stroke="{PALETTE["navy"]}" stroke-width="5"/>',
    ]
    for index, (dx, dy, c) in enumerate([(-92, 35, "blue"), (-40, 19, "teal"), (22, -10, "violet"), (80, -62, "orange")]):
        parts.append(f'<circle cx="{cx + dx}" cy="{cy + dy}" r="15" fill="#FFFFFF" stroke="{color(c)}" stroke-width="5"/>')
        parts.append(text(cx + dx, cy + dy + 5, str(index + 1), 12, 700, color(c), "middle"))
    parts.append(f'<path d="M {cx + 108} {cy - 95} L {cx + 92} {cy - 90} L {cx + 103} {cy - 77}" fill="none" stroke="{PALETTE["navy"]}" stroke-width="5"/>')
    return "".join(parts)


def icon_for(name: str, cx: float, cy: float, accent: str) -> str:
    return {
        "data": icon_data,
        "probe": icon_probe,
        "curve": icon_curve,
        "stress": icon_stress,
    }.get(name, icon_data)(cx, cy, accent)


def _card_positions(stages: list[dict[str, Any]], width: int) -> list[tuple[float, float]]:
    margin, gap = 24.0, 34.0
    weights = [float(stage.get("width_weight", 1.0)) for stage in stages]
    available = width - 2 * margin - gap * (len(stages) - 1)
    unit = available / sum(weights)
    positions: list[tuple[float, float]] = []
    x = margin
    for weight in weights:
        card_width = unit * weight
        positions.append((x, card_width))
        x += card_width + gap
    return positions


def render(spec_path: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    spec = load_yaml(spec_path)
    stages = spec.get("stages", [])
    if not 3 <= len(stages) <= 6:
        raise ValueError("overview needs between 3 and 6 stages")
    width, height = 1800, 900
    card_y, card_h = 92, 530
    positions = _card_positions(stages, width)
    used_colors = {color(stage.get("accent"), "blue") for stage in stages}
    used_colors.update(PALETTE[key] for key in ("navy", "blue", "teal", "orange", "violet", "red"))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="4" stdDeviation="7" flood-color="#5D718A" flood-opacity=".12"/></filter>',
    ]
    for marker_color in used_colors:
        parts.append(
            f'<marker id="arrow-{marker_color[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{marker_color}"/></marker>'
        )
    parts.extend(["</defs>", f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>'])
    parts.append(text(26, 42, spec.get("title", "Research pipeline"), 30, 800))
    if spec.get("status"):
        foreground, background, _ = status_colors(spec.get("status_kind", spec["evidence_status"]))
        parts.append(pill(1370, 12, 402, spec["status"], background, foreground, 42, 20))

    for index, (stage, (x, card_w)) in enumerate(zip(stages, positions), start=1):
        accent = color(stage.get("accent"), "blue")
        background = color(stage.get("background"), "offwhite")
        parts.append(f'<g filter="url(#shadow)">{rounded(x, card_y, card_w, card_h, background, "#D4DFEA", 24, 1.4)}</g>')
        parts.append(pill(x + 22, card_y + 18, 54, str(stage.get("number", index)), accent, "#FFFFFF", 38, 20))
        parts.append(text(x + 88, card_y + 47, stage["title"], 27, 800))
        parts.append(wrapped_text(x + 22, card_y + 82, stage.get("subtitle", ""), card_w - 44, size=20, fill=PALETTE["gray"], max_lines=1))

        blocks = stage.get("blocks")
        if blocks:
            block_top = card_y + 105
            block_height = 184 if len(blocks) == 2 else 128
            for block_index, block in enumerate(blocks):
                by = block_top + block_index * (block_height + 18)
                parts.append(rounded(x + 20, by, card_w - 40, block_height, "#FFFFFF", "#C9D8E7", 16, 1.3))
                block_color = color(block.get("color"), stage.get("accent", "blue"))
                label_width = min(card_w - 68, max(92, 24 + len(block.get("label", "")) * 10))
                parts.append(pill(x + 36, by + 16, label_width, block.get("label", "BRANCH"), color(block.get("light"), "light_blue"), block_color, 34, 18))
                parts.append(wrapped_text(x + 36, by + 81, block.get("title", ""), card_w - 72, size=21, weight=750, max_lines=1))
                if block.get("formula"):
                    parts.append(formula(x + 36, by + 112, card_w - 76, block["formula"], int(block.get("formula_size", 16))))
                if block.get("note"):
                    parts.append(wrapped_text(x + 36, by + block_height - 23, block["note"], card_w - 72, size=17, weight=500, fill=PALETTE["gray"], max_lines=1))
        else:
            if stage.get("formula"):
                parts.append(formula(x + 30, card_y + 145, card_w - 60, stage["formula"], int(stage.get("formula_size", 21))))
                icon_y = card_y + 290
            else:
                icon_y = card_y + 230
            parts.append(icon_for(stage.get("icon", "data"), x + card_w / 2, icon_y, accent))

            tag_x = x + 24
            for tag in stage.get("tags", []):
                label = str(tag.get("label", tag)) if isinstance(tag, dict) else str(tag)
                tag_fill = color(tag.get("fill"), "light_blue") if isinstance(tag, dict) else PALETTE["light_blue"]
                tag_foreground = color(tag.get("color"), stage.get("accent", "blue")) if isinstance(tag, dict) else accent
                tag_width = min(card_w - 48, max(62, 25 + len(label) * 8.3))
                if tag_x + tag_width > x + card_w - 18:
                    break
                parts.append(pill(tag_x, card_y + 382, tag_width, label, tag_fill, tag_foreground, 34, 18))
                tag_x += tag_width + 8
            for line_index, line in enumerate(stage.get("body", [])[:3]):
                strong = bool(line.get("strong")) if isinstance(line, dict) else False
                value = line.get("text", "") if isinstance(line, dict) else str(line)
                line_color = color(line.get("color"), "navy" if strong else "gray") if isinstance(line, dict) else PALETTE["gray"]
                parts.append(wrapped_text(x + 24, card_y + 452 + 38 * line_index, value, card_w - 48, size=20, weight=750 if strong else 450, fill=line_color, max_lines=1))

    for index in range(len(stages) - 1):
        x, card_w = positions[index]
        next_x, _ = positions[index + 1]
        source_stage, target_stage = stages[index], stages[index + 1]
        source_color = color(source_stage.get("accent"), "blue")
        if target_stage.get("blocks") and len(target_stage["blocks"]) >= 2:
            parts.append(arrow(x + card_w, card_y + 250, next_x, card_y + 250, color(target_stage["blocks"][0].get("color"), "violet"), bend=-4, width=2.8))
            parts.append(arrow(x + card_w, card_y + 420, next_x, card_y + 420, color(target_stage["blocks"][1].get("color"), "teal"), bend=4, width=2.8))
        else:
            parts.append(arrow(x + card_w, card_y + 300, next_x, card_y + 300, source_color))

    gate_y, gate_h = 662, 204
    parts.append(rounded(24, gate_y, width - 48, gate_h, "#F7F9FC", "#D4DFEA", 22, 1.4))
    parts.append(text(50, gate_y + 41, spec.get("gate_title", "EVIDENCE GATES"), 22, 800))
    parts.append(text(50, gate_y + 75, spec.get("gate_subtitle", "Freeze criteria before reading final outcomes"), 19, 500, PALETTE["gray"]))
    gates = spec.get("gates", [])
    raw_widths = [max(150, min(420, 46 + len(str(gate.get("label", gate))) * 9.8)) for gate in gates]
    available = width - 100 - max(0, len(gates) - 1) * 14
    scale = min(1.0, available / max(1, sum(raw_widths)))
    gx = 50.0
    for gate, raw_width in zip(gates, raw_widths):
        label = str(gate.get("label", gate)) if isinstance(gate, dict) else str(gate)
        gate_fill = color(gate.get("fill"), "light_blue") if isinstance(gate, dict) else PALETTE["light_blue"]
        gate_color = color(gate.get("color"), "blue") if isinstance(gate, dict) else PALETTE["blue"]
        gate_width = raw_width * scale
        parts.append(pill(gx, gate_y + 116, gate_width, label, gate_fill, gate_color, 42, 18))
        gx += gate_width + 14

    if spec.get("footer"):
        parts.append(text(width - 28, height - 10, spec["footer"], 15, 400, PALETTE["gray"], "end"))
    parts.append("</svg>")
    svg = "\n".join(parts)

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / spec.get("output_name", "overview")
    svg_path = stem.with_suffix(".svg")
    pdf_path = stem.with_suffix(".pdf")
    png_path = stem.with_suffix(".png")
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=str(pdf_path))
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), output_width=2400, output_height=1200)
    write_artifact_manifest(stem, spec_path, spec, [svg_path, pdf_path, png_path])
    return svg_path, pdf_path, png_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in render(args.spec.resolve(), args.output_dir.resolve()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
