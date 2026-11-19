#!/usr/bin/env python3
"""Compose three Looped Transformer comic-style case-study figure demos.

Generated backgrounds are bitmap atmosphere only. Titles, labels, arrows, stage
names, and provenance are native SVG text/paths; real case inserts remain
separate evidence layers.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sources"
GEN = ROOT / "generated"
OUT = ROOT / "rendered"
W, H = 1800, 790


def data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def img(path: Path, x: float, y: float, w: float, h: float, *, opacity: float = 1.0, clip: str | None = None) -> str:
    clip_attr = f' clip-path="url(#{clip})"' if clip else ""
    return f'<image href="{data_uri(path)}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" opacity="{opacity}"{clip_attr}/>'


def text(x: float, y: float, value: str, size: float, *, weight: int = 600, fill: str = "#0D2B6B", anchor: str = "start", italic: bool = False) -> str:
    style = "font-style:italic;" if italic else ""
    return f'<text x="{x}" y="{y}" font-family="Comic Sans MS,Arial,sans-serif" font-size="{size}px" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" style="{style}">{value}</text>'


def rect(x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", sw: float = 1, r: float = 18, opacity: float = 1) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>'


def arrow(x1: float, y1: float, x2: float, y2: float, color: str, label: str, *, bend: float = 0, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="14 10"' if dashed else ""
    path = f'M {x1} {y1} C {(x1+x2)/2} {y1+bend}, {(x1+x2)/2} {y2-bend}, {x2} {y2}'
    mx, my = (x1+x2)/2, (y1+y2)/2
    return f'<path d="{path}" fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round"{dash} marker-end="url(#{color[1:]}-arrow)"/><text x="{mx}" y="{my-12}" font-family="Comic Sans MS,Arial,sans-serif" font-size="22px" font-weight="700" fill="{color}" text-anchor="middle">{label}</text>'


def token_row(x: float, y: float, count: int = 9, active: int = 3) -> str:
    colors = ["#82B8F3", "#A8D4EF", "#F19DBA", "#F4D94E"]
    bits = []
    for i in range(count):
        color = colors[(i + active) % len(colors)]
        bits.append(rect(x + i * 24, y, 18, 28, color, "#0D2B6B", .8, 5))
    return "".join(bits)


def defs() -> str:
    return '''<defs>
      <filter id="wash"><feGaussianBlur stdDeviation="0.35"/></filter>
      <marker id="165DCE-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#165DCE"/></marker>
      <marker id="E84A7A-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#E84A7A"/></marker>
      <marker id="B2174A-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#B2174A"/></marker>
      <marker id="0D2B6B-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#0D2B6B"/></marker>
      <clipPath id="case-clip"><rect x="48" y="190" width="412" height="264" rx="28"/></clipPath>
    </defs>'''


def build(spec: dict) -> str:
    bg = GEN / spec["background"]
    case = SRC / spec["case"]
    extra = [SRC / x for x in spec.get("extra", [])]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', defs(), rect(0, 0, W, H, "#FFFDF8"), img(bg, 0, 0, W, H, opacity=.42), rect(0, 0, W, H, "#FFFFFF", opacity=.28)]
    parts += [text(38, 58, spec["title"], 42, weight=800), text(40, 92, spec["subtitle"], 23, weight=500, fill="#45658F")]
    # real case evidence layer
    parts += [rect(36, 150, 438, 420, "#FFFFFF", "#0D2B6B", 2.4, 28, .86), text(58, 181, "REAL CASE / evidence layer", 21, weight=800, fill="#B2174A"), img(case, 48, 190, 412, 264, clip="case-clip")]
    if extra:
        for i, asset in enumerate(extra[:3]):
            x = 58 + i * 128
            parts.append(img(asset, x, 472, 112, 68, opacity=.98))
    parts += [text(58, 558, spec["source_label"], 17, weight=500, fill="#45658F")]
    # flow stages
    sx = 560
    stage_w = 250
    for i, stage in enumerate(spec["stages"]):
        x = sx + i * 290
        y = 250 + (i % 2) * 40
        parts.append(rect(x, y, stage_w, 150, "#FFFFFF", stage["color"], 3, 28, .93))
        parts.append(text(x + 22, y + 38, stage["label"], 27, weight=800, fill=stage["color"]))
        parts.append(text(x + 22, y + 76, stage["detail"], 20, weight=600, fill="#0D2B6B"))
        parts.append(token_row(x + 22, y + 102, 8, i))
        if i:
            parts.append(arrow(x - 62, y + 76, x - 10, y + 76, "#165DCE", stage.get("link", "UPDATE"), bend=0))
    # loop / refresh arcs
    parts.append(arrow(1310, 445, 850, 450, "#165DCE", spec["loop_label"], bend=80))
    parts.append(arrow(1310, 210, 1440, 188, "#E84A7A", spec["refresh_label"], bend=-55, dashed=True))
    parts.append(rect(1460, 155, 278, 192, "#FFF8FB", "#E84A7A", 2.4, 28, .92))
    parts.append(text(1486, 196, spec["decision"], 26, weight=800, fill="#B2174A"))
    parts.append(text(1486, 235, "STOP → outer sampler", 22, weight=700, fill="#0D2B6B"))
    parts.append(text(1486, 273, spec["boundary"], 18, weight=500, fill="#45658F"))
    parts.append(rect(1410, 500, 330, 90, "#EAF3FF", "none", 0, 30, .88))
    parts.append(text(1575, 540, spec["footer"], 23, weight=700, fill="#0D2B6B", anchor="middle"))
    parts.append(text(1740, 750, "Illustrative design study • native labels/arrows • real case sources preserved", 16, weight=500, fill="#45658F", anchor="end"))
    parts.append("</svg>")
    return "".join(parts)


SPECS = [
    {
        "id": "looped_parkour_refine",
        "background": "parkour_storyboard_bg.png",
        "case": "parkour_rgb.png",
        "extra": ["parkour_flow.png", "parkour_residual.png"],
        "title": "Looped Visual State | Refine without locking in mistakes",
        "subtitle": "A real parkour case enters the loop; internal refinement and new evidence stay visually separate.",
        "source_label": "DAVIS parkour crop • RGB / DIS-flow / RGB residual",
        "stages": [
            {"label":"Evidence", "detail":"RGB + motion cues", "color":"#165DCE", "link":"READ"},
            {"label":"Shared loop", "detail":"same weights, new state", "color":"#0D2B6B", "link":"REFINE"},
            {"label":"Check", "detail":"anchor / conflict / stop", "color":"#B2174A", "link":"DECIDE"},
        ],
        "loop_label":"LOOP / same evidence",
        "refresh_label":"READ / new evidence",
        "decision":"Certified conflict",
        "boundary":"more compute ≠ more evidence",
        "footer":"Revisit the state, not the claim",
    },
    {
        "id": "looped_robot_active_sensing",
        "background": "robot_storyboard_bg.png",
        "case": "robot_assay_plate.jpg",
        "extra": ["robot_assay_plate.jpg"],
        "title": "Looped Active Sensing | Refine the grasp, refresh the view",
        "subtitle": "A laboratory robot uses repeated hidden-state updates, then acquires a new observation when the anchor is stale.",
        "source_label": "Wikimedia Commons / NIAID • public-domain assay-plate photo",
        "stages": [
            {"label":"Observe", "detail":"camera + plate", "color":"#165DCE", "link":"ENCODE"},
            {"label":"Propose", "detail":"shared control loop", "color":"#0D2B6B", "link":"REPAIR"},
            {"label":"Inspect", "detail":"contact / uncertainty", "color":"#B2174A", "link":"CHECK"},
        ],
        "loop_label":"REFINE / same scene",
        "refresh_label":"REFRESH / new view",
        "decision":"Safe grasp?",
        "boundary":"surrogate ≠ physical success",
        "footer":"Read when the state is ambiguous",
    },
    {
        "id": "looped_autonomous_vehicle",
        "background": "vehicle_storyboard_bg.png",
        "case": "autonomous_vehicle.jpg",
        "extra": ["autonomous_vehicle.jpg"],
        "title": "Looped World State | Recheck before committing an action",
        "subtitle": "An autonomous vehicle revises its internal scene state while separating computation from fresh visual evidence.",
        "source_label": "Wikimedia Commons / Dllu • CC BY-SA vehicle image",
        "stages": [
            {"label":"Scene", "detail":"camera + lidar", "color":"#165DCE", "link":"ENCODE"},
            {"label":"Loop", "detail":"shared world state", "color":"#0D2B6B", "link":"REFINE"},
            {"label":"Policy", "detail":"lane / stop / read", "color":"#B2174A", "link":"ACT"},
        ],
        "loop_label":"REFINE / fixed observation",
        "refresh_label":"READ / new frame",
        "decision":"Commit action?",
        "boundary":"more loop ≠ new perception",
        "footer":"Inner loop ≠ outer control",
    },
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for spec in SPECS:
        svg = build(spec)
        svg_path = OUT / f"{spec['id']}.svg"
        pdf_path = OUT / f"{spec['id']}.pdf"
        png_path = OUT / f"{spec['id']}.png"
        svg_path.write_text(svg, encoding="utf-8")
        cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=str(pdf_path), output_width=1800, output_height=790)
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), output_width=1800, output_height=790)
        records.append({"id": spec["id"], "background": f"generated/{spec['background']}", "case": spec["case"], "extra": spec.get("extra", []), "status": "illustrative", "native_text": True, "source_label": spec["source_label"]})
    (OUT / "manifest.json").write_text(json.dumps({"style_pack": "looped_transformer_comic_storyboard", "figures": records}, indent=2) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
