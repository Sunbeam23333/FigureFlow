#!/usr/bin/env python3
"""Render the clean, tiered FigureFlow grammar for the looped case studies.

This renderer intentionally follows the reference FigureFlow composition:
three top modules, three evidence modules, one shared dark artifact, a
full-width training band, and a compact application row. All labels,
connectors, icons, and geometry are native SVG; the real case image is kept as
an evidence layer. Generated comic backgrounds remain in the provenance bundle
but are intentionally omitted from this clean route.
"""

from __future__ import annotations

import base64
import argparse
import html
import json
import sys
from pathlib import Path

# Allow direct execution from any working directory while keeping the renderer
# packaged in FigureFlow's shared `demo_core` namespace.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from demo_core.tiered_pipeline import (
    LAYOUT_ID,
    load_layout,
    output_manifest_entry,
    validate_spec,
    write_outputs,
)


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sources"
OUT = ROOT / "rendered"
W, H = 1600, 1298

NAVY = "#16314D"
BLUE = "#347AC4"
TEAL = "#008C86"
AMBER = "#C78337"
VIOLET = "#7953B4"
MUTED = "#617386"
BORDER = "#D5E0E9"
LIGHT_BLUE = "#F1F6FC"
MINT = "#EEF8F6"
LAVENDER = "#F7F2FC"
CREAM = "#FFF6E9"


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def t(x: float, y: float, value: str, size: float, *, color: str = NAVY, weight: int = 400,
      anchor: str = "start", italic: bool = False) -> str:
    style = "font-style:italic;" if italic else ""
    return (f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial Unicode MS,Arial,sans-serif" '
            f'font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" style="{style}">{esc(value)}</text>')


def multiline(x: float, y: float, lines: list[str], size: float, *, color: str = NAVY,
              weight: int = 400, gap: float = 1.12, anchor: str = "start") -> str:
    return "".join(t(x, y + i * size * gap, line, size, color=color, weight=weight, anchor=anchor)
                   for i, line in enumerate(lines))


def rect(x: float, y: float, w: float, h: float, fill: str, *, stroke: str = "none",
         sw: float = 0, radius: float = 0, opacity: float = 1.0) -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" opacity="{opacity}" rx="{radius}"/>')


def image(path: Path, x: float, y: float, w: float, h: float, *, clip: str | None = None,
          opacity: float = 1.0) -> str:
    clip_attr = f' clip-path="url(#{clip})"' if clip else ""
    return (f'<image href="{data_uri(path)}" x="{x}" y="{y}" width="{w}" height="{h}" '
            f'preserveAspectRatio="xMidYMid slice" opacity="{opacity}"{clip_attr}/>')


def line(x1: float, y1: float, x2: float, y2: float, color: str, *, sw: float = 3,
         dashed: bool = False) -> str:
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    return f'<path d="M {x1} {y1} L {x2} {y2}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"{dash}/>'


def elbow(points: list[tuple[float, float]], color: str, *, marker: str = "arrow",
          sw: float = 3, dot: tuple[float, float] | None = None) -> str:
    d = "M " + " L ".join(f"{x} {y}" for x, y in points)
    out = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#{marker}-{color[1:]})"/>'
    if dot:
        out += f'<circle cx="{dot[0]}" cy="{dot[1]}" r="5" fill="{color}"/>'
    return out


def panel(x: float, y: float, w: float, h: float, fill: str, accent: str, title: str,
          *, title_size: float = 38) -> str:
    return (rect(x, y, w, h, fill, stroke=BORDER, sw=1.3, radius=18)
            + rect(x + 20, y + 19, 5, 40, accent, radius=2)
            + t(x + 39, y + 56, title, title_size, weight=700))


def icon_camera(x: float, y: float, color: str, scale: float = 1.0) -> str:
    w, h = 34 * scale, 24 * scale
    return (f'<g transform="translate({x},{y}) scale({scale})" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="0" y="4" width="29" height="20" rx="4"/><path d="M29 10l11-6v20l-11-6z"/><circle cx="14" cy="14" r="5"/></g>')


def icon_loop(x: float, y: float, color: str, scale: float = 1.0) -> str:
    return (f'<g transform="translate({x},{y}) scale({scale})" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M10 8a12 12 0 0 1 18 2"/><path d="M28 10l-1-7 7 2"/><path d="M30 24a12 12 0 0 1-18-2"/><path d="M12 22l1 7-7-2"/></g>')


def icon_target(x: float, y: float, color: str, scale: float = 1.0) -> str:
    return (f'<g transform="translate({x},{y}) scale({scale})" fill="none" stroke="{color}" stroke-width="2.3" stroke-linecap="round">'
            '<circle cx="18" cy="18" r="14"/><circle cx="18" cy="18" r="6"/><path d="M18 1v6M18 29v6M1 18h6M29 18h6"/></g>')


def icon_stop(x: float, y: float, color: str, scale: float = 1.0) -> str:
    return (f'<g transform="translate({x},{y}) scale({scale})" fill="none" stroke="{color}" stroke-width="2.3" stroke-linejoin="round">'
            '<path d="M18 2l16 16-16 16L2 18z"/><path d="M12 18h12"/></g>')


def icon_database(x: float, y: float, color: str, scale: float = 1.0) -> str:
    return (f'<g transform="translate({x},{y}) scale({scale})" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round">'
            '<ellipse cx="18" cy="7" rx="14" ry="5"/><path d="M4 7v20c0 3 28 3 28 0V7"/><path d="M4 17c0 3 28 3 28 0"/></g>')


def token_row(x: float, y: float, color: str, n: int = 6, *, width: float = 21, height: float = 23) -> str:
    parts = []
    for i in range(n):
        opacity = [0.18, 0.30, 0.45, 0.65, 0.82, 1.0][i % 6]
        parts.append(rect(x + i * (width + 6), y, width, height, color, radius=4, opacity=opacity))
    return "".join(parts)


def defs() -> str:
    return '''<defs>
      <marker id="arrow-347AC4" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#347AC4"/></marker>
      <marker id="arrow-008C86" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#008C86"/></marker>
      <marker id="arrow-C78337" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#C78337"/></marker>
      <marker id="arrow-7953B4" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#7953B4"/></marker>
      <clipPath id="case-main"><rect x="50" y="110" width="244" height="150" rx="10"/></clipPath>
      <clipPath id="case-small-a"><rect x="67" y="548" width="70" height="48" rx="7"/></clipPath>
      <clipPath id="case-small-b"><rect x="150" y="548" width="70" height="48" rx="7"/></clipPath>
      <clipPath id="case-small-c"><rect x="233" y="548" width="70" height="48" rx="7"/></clipPath>
    </defs>'''


def build(spec: dict) -> str:
    case = SRC / spec["case"]
    extra = [SRC / x for x in spec.get("extra", [])]
    out: list[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', defs(), rect(0, 0, W, H, "#FFFFFF")]
    # Keep the generated comic as a quiet storyboard cue in the state panel.
    out.append(panel(32, 28, 280, 300, "#FFFFFF", BLUE, "REAL CASE", title_size=34))
    out.append(panel(354, 28, 454, 300, LIGHT_BLUE, BLUE, spec["top_middle"], title_size=36))
    out.append(panel(850, 28, 718, 300, "#FFFFFF", TEAL, spec["top_right"], title_size=36))
    out.append(image(case, 50, 110, 244, 150, clip="case-main"))
    out.append(rect(50, 110, 244, 150, "none", stroke=BORDER, sw=1, radius=10))
    out.append(t(50, 286, spec["case_caption"], 16, color=MUTED))
    # middle top: observe/encode icons
    for i, item in enumerate(spec["observe"]):
        # Three semantic columns inside the 454px card.  Keep the icon and
        # label centers on a fixed grid; long labels are authored as short
        # semantic tokens in the case spec rather than squeezed by the
        # renderer.
        cx = 404 + i * 140
        icon, label, detail = item
        if icon == "camera":
            out.append(icon_camera(cx, 125, BLUE, 0.9))
        elif icon == "loop":
            out.append(icon_loop(cx, 122, BLUE, 0.9))
        elif icon == "target":
            out.append(icon_target(cx, 122, BLUE, 0.9))
        label_size = 18 if len(label) > 8 else 21
        detail_size = 15 if len(detail) > 10 else 17
        out.append(t(cx + 20, 206, label, label_size, anchor="middle"))
        out.append(t(cx + 20, 239, detail, detail_size, color=MUTED, anchor="middle"))
    # The reference grammar is vector-first.  Generated comic backgrounds are
    # retained in the provenance bundle and in the earlier storyboard route,
    # but are intentionally absent from this clean tiered reproduction.
    for i, item in enumerate(spec["states"]):
        cx = 938 + i * 204
        icon, label, detail, color = item
        if icon == "loop":
            out.append(icon_loop(cx, 121, color, 0.9))
        elif icon == "target":
            out.append(icon_target(cx, 121, color, 0.9))
        else:
            out.append(icon_stop(cx, 121, color, 0.9))
        out.append(t(cx + 20, 212, label, 23, anchor="middle", color=color, weight=700))
        out.append(multiline(cx + 20, 246, detail, 18, color=MUTED, anchor="middle"))
    out.append(rect(1038, 284, 430, 28, "#EEF8F6", radius=6))
    out.append(t(1253, 305, spec["state_band"], 19, color=TEAL, anchor="middle", weight=700))
    # top connectors
    out.append(elbow([(312, 178), (338, 178), (338, 178), (354, 178)], BLUE))
    out.append(elbow([(808, 178), (830, 178), (830, 178), (850, 178)], BLUE))

    # middle evidence tier
    out.append(panel(32, 426, 480, 308, CREAM, AMBER, spec["middle_left"], title_size=36))
    out.append(panel(544, 426, 446, 308, MINT, TEAL, spec["middle_mid"], title_size=36))
    out.append(panel(1022, 426, 546, 308, LAVENDER, VIOLET, spec["middle_right"], title_size=36))
    # timeline thumbnails and captions
    for i in range(5):
        x = 67 + i * 83
        if i == 0:
            out.append(image(case, x, 548, 70, 48, clip="case-small-a"))
        elif i == 1 and extra:
            out.append(image(extra[0], x, 548, 70, 48, clip="case-small-b"))
        elif i == 2 and len(extra) > 1:
            out.append(image(extra[1], x, 548, 70, 48, clip="case-small-c"))
        else:
            out.append(rect(x, 548, 70, 48, "#D7C8B5", radius=7, opacity=.66))
        out.append(rect(x, 548, 70, 48, "none", stroke="#FFFFFF", sw=2, radius=7))
    out.append(t(67, 530, spec["timeline_caption"], 22, color=AMBER))
    out.append(multiline(63, 646, spec["timeline_body"], 22, gap=1.35))
    # paired evidence panel
    out.append(icon_camera(608, 551, TEAL, 1.2))
    out.append(t(650, 608, "case", 24, anchor="middle"))
    out.append(t(755, 592, "+", 40, color=TEAL, anchor="middle"))
    out.append(icon_loop(830, 551, TEAL, 1.2))
    out.append(t(876, 608, "state", 24, anchor="middle"))
    out.append(t(766, 690, spec["pair_caption"], 23, color=TEAL, anchor="middle", weight=700))
    # decision panel
    out.append(icon_target(1092, 551, VIOLET, 1.0))
    out.append(t(1137, 612, spec["decision_left"], 23, anchor="middle"))
    out.append(line(1195, 575, 1298, 575, VIOLET, sw=3))
    out.append(elbow([(1195, 575), (1298, 575)], VIOLET))
    out.append(icon_stop(1340, 551, VIOLET, 1.0))
    out.append(t(1391, 612, spec["decision_right"], 23, anchor="middle"))
    out.append(t(1296, 690, spec["decision_caption"], 23, color=VIOLET, anchor="middle", weight=700))

    # evidence to shared artifact
    out.append(elbow([(272, 328), (272, 394), (272, 394), (272, 426)], AMBER, dot=(272, 394)))
    out.append(t(286, 385, "observed case", 18, color=AMBER))
    out.append(elbow([(630, 328), (630, 392), (630, 392), (768, 392), (768, 426)], TEAL, dot=(630, 392)))
    out.append(elbow([(1209, 328), (1209, 392), (1209, 392), (1295, 392), (1295, 426)], VIOLET, dot=(1209, 392)))
    # shared artifact / convergence bar
    out.append(rect(341, 790, 918, 79, NAVY, radius=15))
    out.append(icon_database(374, 807, "#FFFFFF", .95))
    # Keep the title within the left half of the dark bar; the right half is
    # reserved for the explicit artifact fields.
    shared_size = 27 if len(spec["shared_title"]) > 16 else 30
    field_size = 22 if len(spec["shared_fields"]) > 23 else 26
    out.append(t(442, 844, spec["shared_title"], shared_size, color="#FFFFFF", weight=700))
    out.append(rect(739, 809, 2, 39, "#7794AB"))
    out.append(t(790, 845, spec["shared_fields"], field_size, color="#FFFFFF"))
    out.append(elbow([(272, 734), (272, 766), (470, 766), (470, 790)], AMBER, dot=(272, 766)))
    out.append(elbow([(768, 734), (768, 790)], TEAL))
    out.append(elbow([(1295, 734), (1295, 766), (1130, 766), (1130, 790)], VIOLET, dot=(1295, 766)))
    # training band: title/header lane is kept separate from the two data
    # lanes.  This is the key PPT discipline that the earlier comic version
    # lacked and prevents labels from colliding with token rows.
    out.append(panel(32, 916, 1536, 222, LIGHT_BLUE, BLUE, spec["training_title"], title_size=31))
    out.append(t(58, 1038, "REFINE", 22, color=BLUE, weight=700))
    out.append(t(58, 1109, "REFRESH", 22, color=TEAL, weight=700))
    out.append(t(505, 997, "state token", 18, color=BLUE))
    out.append(t(758, 997, "normalized state", 18, color=BLUE))
    for lane, color, y in [(0, BLUE, 1023), (1, TEAL, 1094)]:
        out.append(rect(245, y - 18, 204, 57, "#FFFFFF", stroke=color, sw=1.5, radius=9))
        out.append(t(347, y + 18, "shared loop" if lane == 0 else "new evidence", 21, color=color, anchor="middle", weight=700))
        out.append(elbow([(205, y + 10), (245, y + 10)], color))
        out.append(token_row(505, y, color))
        out.append(elbow([(449, y + 10), (505, y + 10)], color))
        out.append(token_row(758, y - 5, color, n=6, width=18, height=29))
        out.append(elbow([(649, y + 10), (758, y + 10)], color))
    out.append(rect(1020, 996, 230, 126, "#FFFFFF", stroke=BLUE, sw=1.6, radius=12))
    out.append(icon_target(1098, 1008, BLUE, .65))
    out.append(t(1135, 1090, spec["loss_label"], 22, anchor="middle", weight=700))
    out.append(elbow([(896, 1033), (1020, 1033)], BLUE))
    out.append(elbow([(896, 1104), (965, 1104), (965, 1070), (1020, 1070)], TEAL))
    out.append(icon_database(1320, 982, MUTED, .78))
    out.append(multiline(1372, 1060, ["case memory", "cross-step negatives"], 18, color=MUTED))
    # convergence to training + application row
    out.append(t(832, 907, "train from shared artifact", 20, color=BLUE))
    out.append(elbow([(800, 869), (800, 916)], BLUE))
    out.append(rect(32, 1185, 5, 58, VIOLET, radius=2))
    out.append(t(52, 1234, spec["application_title"], 30, weight=700))
    out.append(token_row(315, 1198, VIOLET, n=6, width=18, height=30))
    out.append(t(465, 1232, spec["application_embedding"], 25, color=VIOLET, weight=700))
    out.append(elbow([(925, 1138), (925, 1170), (860, 1170), (860, 1216)], VIOLET))
    out.append(icon_target(860, 1197, VIOLET, .72))
    out.append(t(910, 1232, spec["application_left"], 21))
    out.append(icon_loop(1170, 1197, VIOLET, .72))
    out.append(t(1228, 1232, spec["application_right"], 21))
    out.append(t(1563, 1277, "illustrative · case-grounded workflow", 18, color=MUTED, anchor="end"))
    out.append("</svg>")
    return "".join(out)


SPECS = [
    {
        "id": "looped_parkour_refine",
        "background": "parkour_storyboard_bg.png",
        "case": "parkour_rgb.png",
        "extra": ["parkour_flow.png", "parkour_residual.png"],
        "case_caption": "project crop · RGB / flow / residual",
        "top_middle": "OBSERVE + ENCODE",
        "top_right": "LOOPED STATE",
        "observe": [("camera", "RGB", "appearance"), ("loop", "FLOW", "motion"), ("target", "RESIDUAL", "conflict")],
        "states": [("loop", "REFINE", ["same evidence", "shared weights"], BLUE), ("target", "CHECK", ["anchor / conflict", "state quality"], TEAL), ("stop", "STOP", ["outer sampler", "new evidence"], VIOLET)],
        "state_band": "revisit the state, not the claim",
        "middle_left": "CASE TIMELINE",
        "middle_mid": "PAIRED EVIDENCE",
        "middle_right": "DECISION GATE",
        "timeline_caption": "five frames from one parkour case",
        "timeline_body": ["nearby frames: positive", "non-adjacent: hard negative", "content check remains explicit"],
        "pair_caption": "RGB + shared hidden state",
        "decision_left": "anchor check",
        "decision_right": "certified conflict",
        "decision_caption": "stop before inventing evidence",
        "shared_title": "CERTIFIED STATE",
        "shared_fields": "rgb / flow / residual",
        "training_title": "SHARED LOOP",
        "loss_label": "state consistency",
        "application_title": "APPLICATION",
        "application_embedding": "state embedding",
        "application_left": "retrieve matching motion",
        "application_right": "sequence-aware action",
    },
    {
        "id": "looped_robot_active_sensing",
        "background": "robot_storyboard_bg.png",
        "case": "robot_assay_plate.jpg",
        "extra": ["robot_assay_plate.jpg"],
        "case_caption": "Wikimedia / NIAID · public-domain assay plate",
        "top_middle": "OBSERVE + ENCODE",
        "top_right": "LOOPED GRASP STATE",
        "observe": [("camera", "VIEW", "plate view"), ("loop", "GRASP", "contact state"), ("target", "UNCERT.", "anchor")],
        "states": [("loop", "REFINE", ["same view", "shared control"], BLUE), ("target", "INSPECT", ["contact / uncertainty", "physical check"], TEAL), ("stop", "REFRESH", ["new view", "outer sampler"], VIOLET)],
        "state_band": "read when the state is ambiguous",
        "middle_left": "CASE TIMELINE",
        "middle_mid": "PAIRED EVIDENCE",
        "middle_right": "DECISION GATE",
        "timeline_caption": "observe → propose → inspect",
        "timeline_body": ["camera view is evidence", "latent repair is computation", "contact check is a gate"],
        "pair_caption": "plate view + grasp state",
        "decision_left": "contact check",
        "decision_right": "safe grasp?",
        "decision_caption": "surrogate ≠ physical success",
        "shared_title": "CERTIFIED GRASP",
        "shared_fields": "view · contact · uncertainty",
        "training_title": "SHARED CONTROL",
        "loss_label": "grasp consistency",
        "application_title": "APPLICATION",
        "application_embedding": "grasp embedding",
        "application_left": "select safe approach",
        "application_right": "sequence-aware control",
    },
    {
        "id": "looped_autonomous_vehicle",
        "background": "vehicle_storyboard_bg.png",
        "case": "autonomous_vehicle.jpg",
        "extra": ["autonomous_vehicle.jpg"],
        "case_caption": "Wikimedia / Maxx@night · CC BY 2.0",
        "top_middle": "OBSERVE + ENCODE",
        "top_right": "LOOPED WORLD STATE",
        "observe": [("camera", "VIEW", "scene"), ("loop", "LIDAR", "geometry"), ("target", "POLICY", "action")],
        "states": [("loop", "REFINE", ["fixed observation", "shared state"], BLUE), ("target", "RECHECK", ["lane / stop", "policy gate"], TEAL), ("stop", "READ", ["new frame", "outer control"], VIOLET)],
        "state_band": "inner loop ≠ outer control",
        "middle_left": "CASE TIMELINE",
        "middle_mid": "PAIRED EVIDENCE",
        "middle_right": "DECISION GATE",
        "timeline_caption": "scene → loop → policy",
        "timeline_body": ["camera + lidar are evidence", "state repair is computation", "action remains gated"],
        "pair_caption": "scene evidence + world state",
        "decision_left": "lane / stop check",
        "decision_right": "commit action?",
        "decision_caption": "more loop ≠ new perception",
        "shared_title": "CERTIFIED WORLD",
        "shared_fields": "camera / lidar / policy",
        "training_title": "SHARED WORLD MODEL",
        "loss_label": "state alignment",
        "application_title": "APPLICATION",
        "application_embedding": "world-state embedding",
        "application_left": "semantic scene search",
        "application_right": "sequence-aware policy",
    },
]


def main(output_dir: Path = OUT) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    load_layout()
    records = []
    for spec in SPECS:
        validate_spec(spec)
        svg = build(spec)
        svg_path = output_dir / f"{spec['id']}.svg"
        pdf_path = output_dir / f"{spec['id']}.pdf"
        png_path = output_dir / f"{spec['id']}.png"
        review_path = output_dir / f"{spec['id']}_review.png"
        write_outputs(svg, svg_path, pdf_path, png_path, width=W, height=H, review_png_path=review_path)
        entry = output_manifest_entry(spec, root=SRC)
        entry.update({
            "pdf": pdf_path.name,
            "delivery_png": png_path.name,
            "review_png": review_path.name,
            "paper_include_width_pt": 540,
            "canvas": [W, H],
        })
        records.append(entry)
    (output_dir / "manifest.json").write_text(json.dumps({"layout": LAYOUT_ID, "figures": records}, indent=2) + "\n", encoding="utf-8")
    layout = load_layout()
    (output_dir / "tiered_scene.json").write_text(
        json.dumps(
            {
                "schema": "figureflow.tiered-native.v1",
                "layout": layout,
                "evidence_status": "illustrative",
                "figures": [{"id": spec["id"], "case": spec["case"], "case_caption": spec["case_caption"]} for spec in SPECS],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output_dir)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT, help="directory for SVG/PDF/PNG/manifest outputs")
    raise SystemExit(main(parser.parse_args().output_dir))
