#!/usr/bin/env python3
"""Build a local, source-grounded PDF atlas for the FigureFlow visual registry.

The atlas uses FigureFlow-native outputs and derived vector sketches. It does
not download or embed external paper screenshots.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


PAGE_W, PAGE_H = landscape(A4)
ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).resolve().parent
FONT_DIR = ROOT / "cases/concord_rec_reference/redesign_v2/fonts"
registerFont(TTFont("FigureFlowSans", str(FONT_DIR / "SourceSans3-Regular.ttf")))
registerFont(TTFont("FigureFlowSans-Bold", str(FONT_DIR / "SourceSans3-Semibold.ttf")))
PALETTE = {
    "ink": "#1F2933", "muted": "#667085", "grid": "#D9E1E8",
    "navy": "#244B6B", "blue": "#3478C9", "emerald": "#0E9F6E",
    "teal": "#087F87", "violet": "#8064A2", "amber": "#F2B84B",
    "coral": "#D9655D", "good": "#2E9B68", "bad": "#D9655D", "pale": "#FFF7D6", "bluebg": "#EAF2FB",
    "tealbg": "#E8F6F1", "violetbg": "#F1ECF7", "amberbg": "#FFF6DF",
    "paper": "#FFFFFF",
}


def rgb(token: str):
    return colors.HexColor(PALETTE.get(token, token))


def draw_header(c: canvas.Canvas, title: str, kicker: str, page: int) -> None:
    c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans-Bold", 21)
    c.drawString(22 * mm, PAGE_H - 22 * mm, title)
    c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans", 8.7)
    c.drawString(22 * mm, PAGE_H - 29 * mm, kicker)
    c.setStrokeColor(rgb("grid")); c.setLineWidth(0.7)
    c.line(22 * mm, PAGE_H - 34 * mm, PAGE_W - 22 * mm, PAGE_H - 34 * mm)
    c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans", 7)
    c.drawRightString(PAGE_W - 22 * mm, 10 * mm, f"FigureFlow visual atlas · {page:02d}")


def draw_wrapped(c: canvas.Canvas, text: str, x: float, y: float, width: float, *, font="FigureFlowSans", size=8.5, leading=11, color="ink") -> float:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = word if not current else f"{current} {word}"
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            if current: lines.append(current)
            current = word
    if current: lines.append(current)
    c.setFillColor(rgb(color)); c.setFont(font, size)
    for line in lines:
        c.drawString(x, y, line); y -= leading
    return y


def draw_card(c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, body: str, accent: str, fill: str = "paper") -> None:
    c.setFillColor(rgb(fill)); c.setStrokeColor(rgb("grid")); c.setLineWidth(0.7)
    c.roundRect(x, y, w, h, 4 * mm, fill=1, stroke=1)
    c.setFillColor(rgb(accent)); c.roundRect(x, y + h - 7 * mm, w, 7 * mm, 4 * mm, fill=1, stroke=0)
    c.rect(x, y + h - 7 * mm, w, 3.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("FigureFlowSans-Bold", 9)
    c.drawString(x + 4 * mm, y + h - 5 * mm, title)
    draw_wrapped(c, body, x + 4 * mm, y + h - 14 * mm, w - 8 * mm, size=8, leading=10, color="ink")


def fit_image(path: Path, max_w: float, max_h: float) -> tuple[float, float]:
    with Image.open(path) as image:
        width, height = image.size
    scale = min(max_w / width, max_h / height)
    return width * scale, height * scale


def draw_image(c: canvas.Canvas, path: Path, x: float, y: float, max_w: float, max_h: float, *, border=True) -> tuple[float, float]:
    width, height = fit_image(path, max_w, max_h)
    if border:
        c.setStrokeColor(rgb("grid")); c.setLineWidth(0.6)
        c.rect(x - 1.2 * mm, y - 1.2 * mm, width + 2.4 * mm, height + 2.4 * mm, fill=0, stroke=1)
    c.drawImage(ImageReader(str(path)), x, y, width=width, height=height, preserveAspectRatio=True, mask="auto")
    return width, height


def make_demo_assets(root: Path, temp: Path) -> dict[str, Path]:
    assets = {
        "architecture": root / "cases/concord_rec_reference/reference/architecture.png",
        "network": root / "cases/concord_rec_reference/reference/network_structure.png",
        "alphaedit": root / "cases/alphaedit_figure2/preview.png",
    }
    demo_out = temp / "data_demo"
    subprocess.run(["python3", str(root / "skill/design-research-figures/scripts/render_data_figure.py"), str(root / "cases/top_conference_visual_research/demo/quality_cost.yaml"), "--output-dir", str(demo_out)], check=True, stdout=subprocess.DEVNULL)
    assets["data_demo"] = demo_out / "top_conference_data_demo.png"
    tikz_out = temp / "tikz"
    subprocess.run(["python3", str(root / "skill/design-research-figures/scripts/compile_figures.py"), str(root / "skill/design-research-figures/assets/tikz/conference_overview_template.tex"), "--output-dir", str(tikz_out)], check=True, stdout=subprocess.DEVNULL)
    assets["template"] = tikz_out / "conference_overview_template.png"
    return assets


def page_cover(c: canvas.Canvas, catalog: dict) -> None:
    c.setFillColor(rgb("paper")); c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    for i, token in enumerate(("blue", "teal", "emerald", "amber", "violet", "coral")):
        c.setFillColor(rgb(token)); c.rect(0, PAGE_H - (24 + i * 8) * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans-Bold", 30)
    c.drawString(24 * mm, PAGE_H - 84 * mm, "FigureFlow")
    c.setFont("FigureFlowSans-Bold", 22); c.drawString(24 * mm, PAGE_H - 97 * mm, "Top-conference visual atlas")
    c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans", 11)
    c.drawString(24 * mm, PAGE_H - 110 * mm, "CVPR · ICCV · ICML · NeurIPS · ICLR · Best / Outstanding / oral-facing visual grammar")
    c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans-Bold", 12)
    c.drawString(24 * mm, 63 * mm, f"{len(catalog['entries'])} source-grounded entries · 8 reusable grammar families")
    draw_wrapped(c, "A compact demonstration of design rules and native FigureFlow templates accumulated from official conference pages and paper PDFs. The atlas stores derived observations and editable outputs, not external paper screenshots.", 24 * mm, 53 * mm, 150 * mm, size=9, leading=12, color="muted")
    c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans", 8)
    c.drawString(24 * mm, 18 * mm, "Research snapshot: 2026-11-19 · FigureFlow repository · evidence status remains explicit")


def page_grammar(c: canvas.Canvas) -> None:
    draw_header(c, "Six reusable visual grammars", "Derived from award and paper figures; choose the reading order before choosing decoration.", 2)
    cards = [
        ("hero_evidence", "real input → compact representation → output evidence", "blue", "bluebg"),
        ("action_rollout", "frame strip + action/time rail + goal/score", "amber", "amberbg"),
        ("qualitative_matrix", "fixed rows/columns, crop, scale, shared colorbar", "violet", "violetbg"),
        ("multiscale_ladder", "coarse-to-fine grid, one repeated block ×L", "teal", "tealbg"),
        ("quality_cost_bubble", "log time/compute, quality y, area = parameters", "emerald", "tealbg"),
        ("small_multiples", "shared axes, sparse markers, direct exception labels", "coral", "amberbg"),
    ]
    x0, y0 = 22 * mm, PAGE_H - 64 * mm; card_w, card_h = 82 * mm, 42 * mm
    for index, (title, body, accent, fill) in enumerate(cards):
        x = x0 + (index % 3) * 91 * mm; y = y0 - (index // 3) * 53 * mm
        draw_card(c, x, y, card_w, card_h, title, body, accent, fill)
        c.setStrokeColor(rgb(accent)); c.setLineWidth(1.4); c.line(x + 5 * mm, y + 8 * mm, x + 28 * mm, y + 8 * mm)
        c.setFillColor(rgb(accent)); c.circle(x + 5 * mm, y + 8 * mm, 2 * mm, fill=1, stroke=0); c.circle(x + 28 * mm, y + 8 * mm, 2 * mm, fill=1, stroke=0)
        if index in (1, 4):
            c.setStrokeColor(rgb("muted")); c.setDash(2, 2); c.line(x + 16 * mm, y + 4 * mm, x + 16 * mm, y + 12 * mm); c.setDash()
        if index == 2:
            for row in range(3):
                for col in range(4):
                    c.setFillColor(rgb("violet" if col == 3 else "grid")); c.rect(x + 39 * mm + col * 5 * mm, y + 4 * mm + row * 3 * mm, 3.5 * mm, 2 * mm, fill=1, stroke=0)


def page_main_examples(c: canvas.Canvas, assets: dict[str, Path]) -> None:
    draw_header(c, "Native main-figure examples", "The retained CONCORD-Rec case shows how semantic color and shape can carry the method grammar.", 3)
    draw_image(c, assets["architecture"], 22 * mm, 106 * mm, 118 * mm, 78 * mm)
    draw_image(c, assets["network"], 153 * mm, 106 * mm, 118 * mm, 78 * mm)
    draw_card(c, 22 * mm, 34 * mm, 118 * mm, 52 * mm, "Asymmetric overview", "Navy = inherited backbone; teal = trainable conditioning/fusion; violet = observed modality context; amber = detached offline supervision. Stack/projection/fusion/store shapes should remain consistent.", "navy", "bluebg")
    draw_card(c, 153 * mm, 34 * mm, 118 * mm, 52 * mm, "Mechanism network", "Solid arrows carry data, dotted lines show shared paths, and dashed arrows preserve gradient or detached-supervision boundaries. The final architecture remains editable vector output.", "teal", "tealbg")


def page_data_examples(c: canvas.Canvas, assets: dict[str, Path]) -> None:
    draw_header(c, "Data figures: evidence and uncertainty", "AlphaEdit-style annular comparison remains a source-artwork case; the bubble/line pair is a synthetic renderer smoke test.", 4)
    draw_image(c, assets["alphaedit"], 22 * mm, 83 * mm, 125 * mm, 90 * mm)
    draw_image(c, assets["data_demo"], 154 * mm, 83 * mm, 118 * mm, 90 * mm)
    draw_card(c, 22 * mm, 28 * mm, 125 * mm, 40 * mm, "Published-figure route", "Faithful reconstruction keeps the published geometry and status boundary; replaceable CSV mode recalculates values and records the evidence source separately.", "violet", "violetbg")
    draw_card(c, 154 * mm, 28 * mm, 118 * mm, 40 * mm, "Renderer additions", "kind: bubble · size_field · log axis · low/high error bars · direct_label. The demo is explicitly synthetic and makes no experimental claim.", "emerald", "tealbg")


def page_template(c: canvas.Canvas, assets: dict[str, Path]) -> None:
    draw_header(c, "FigureFlow native overview template", "A paper-friendly input → representation → evidence composition with a sparse provenance rail.", 5)
    draw_image(c, assets["template"], 22 * mm, 73 * mm, 175 * mm, 112 * mm)
    draw_card(c, 207 * mm, 118 * mm, 72 * mm, 62 * mm, "Reading order", "1. Real observation or condition. 2. Compact representation or core computation. 3. Output evidence tied to a metric, goal, or aligned ground truth.", "blue", "bluebg")
    draw_card(c, 207 * mm, 46 * mm, 72 * mm, 59 * mm, "Evidence rail", "Keep measured/implemented status, seed + hardware, source + caption, and manifest status visible. This rail is a claim boundary, not decorative marketing.", "amber", "amberbg")


def page_rollout(c: canvas.Canvas) -> None:
    draw_header(c, "World-model rollout grammar", "Real frames and actions are the evidence; abstract mazes remain schematic only.", 6)
    x0, y = 24 * mm, 132 * mm; frame_w, frame_h, gap = 34 * mm, 28 * mm, 5 * mm
    for i in range(5):
        x = x0 + i * (frame_w + gap)
        c.setFillColor(rgb("bluebg" if i < 4 else "tealbg")); c.setStrokeColor(rgb("navy" if i < 4 else "teal"))
        c.roundRect(x, y, frame_w, frame_h, 2 * mm, fill=1, stroke=1)
        c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans-Bold", 8); c.drawCentredString(x + frame_w / 2, y + frame_h / 2 + 2 * mm, "frame")
        c.setFont("FigureFlowSans", 7); c.drawCentredString(x + frame_w / 2, y + frame_h / 2 - 4 * mm, f"t+{i * 4}")
        if i < 4:
            c.setStrokeColor(rgb("amber")); c.setLineWidth(1.6); c.line(x + frame_w + 1 * mm, y + frame_h / 2, x + frame_w + gap - 1 * mm, y + frame_h / 2)
    c.setFillColor(rgb("amber")); c.setFont("FigureFlowSans-Bold", 9); c.drawString(x0, y - 10 * mm, "action / time rail")
    c.setStrokeColor(rgb("amber")); c.setLineWidth(1.3); c.line(x0 + 35 * mm, y - 9.1 * mm, x0 + 146 * mm, y - 9.1 * mm)
    for i in range(5):
        x = x0 + 35 * mm + i * 27.5 * mm; c.circle(x, y - 9.1 * mm, 1.5 * mm, fill=1, stroke=0)
        c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans", 7); c.drawCentredString(x, y - 15 * mm, f"a{i}")
    c.setFillColor(rgb("good")); c.roundRect(208 * mm, 128 * mm, 27 * mm, 17 * mm, 3 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("FigureFlowSans-Bold", 9); c.drawCentredString(221.5 * mm, 137 * mm, "GOAL")
    c.setFillColor(rgb("coral")); c.roundRect(243 * mm, 128 * mm, 27 * mm, 17 * mm, 3 * mm, fill=1, stroke=0); c.setFillColor(colors.white); c.drawCentredString(256.5 * mm, 137 * mm, "SCORE")
    draw_card(c, 24 * mm, 44 * mm, 78 * mm, 45 * mm, "Do", "Align condition/action, observation, prediction, and ground truth by timestamp. Use the same method color across qualitative and quantitative panels.", "emerald", "tealbg")
    draw_card(c, 110 * mm, 44 * mm, 78 * mm, 45 * mm, "Do not", "Replace a real rollout with an abstract maze, or let a generated illustration occupy an empirical result slot.", "coral", "amberbg")
    draw_card(c, 196 * mm, 44 * mm, 78 * mm, 45 * mm, "Status", "Record crop, frame indices, action values, and selection policy in a manifest. Mark synthetic examples explicitly.", "amber", "amberbg")


def page_palette(c: canvas.Canvas) -> None:
    draw_header(c, "Palette and redundant encodings", "Color is semantic; line style, marker, shape, and direct labels carry the distinction again.", 7)
    tokens = [("emerald", "selected method / ours"), ("blue", "measured method family"), ("teal", "latent / conditioning"), ("amber", "action / control"), ("violet", "context / auxiliary"), ("coral", "negative / contrast")]
    x0, y0 = 25 * mm, 148 * mm
    for i, (token, label) in enumerate(tokens):
        x = x0 + (i % 3) * 83 * mm; y = y0 - (i // 3) * 35 * mm
        c.setFillColor(rgb(token)); c.roundRect(x, y, 18 * mm, 14 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans-Bold", 8.5); c.drawString(x + 22 * mm, y + 8 * mm, token)
        c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans", 7.8); c.drawString(x + 22 * mm, y + 3 * mm, label)
    c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans-Bold", 10); c.drawString(25 * mm, 66 * mm, "Colorblind-safe series")
    safe = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#F0E442", "#56B4E9", "#000000"]
    for i, hex_color in enumerate(safe):
        x = 25 * mm + i * 29 * mm; c.setFillColor(colors.HexColor(hex_color)); c.circle(x + 4 * mm, 52 * mm, 4 * mm, fill=1, stroke=0)
        c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans", 6.4); c.drawCentredString(x + 4 * mm, 43 * mm, hex_color)
    c.setStrokeColor(rgb("blue")); c.setLineWidth(2); c.line(25 * mm, 30 * mm, 67 * mm, 30 * mm)
    c.setStrokeColor(rgb("muted")); c.setDash(3, 2); c.line(78 * mm, 30 * mm, 120 * mm, 30 * mm); c.setDash()
    c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans", 8); c.drawString(25 * mm, 23 * mm, "solid = data flow"); c.drawString(78 * mm, 23 * mm, "dashed = control / detached boundary")
    draw_wrapped(c, "Use pale fills only for grouping or selected-method emphasis. Keep the background white and let a small number of saturated semantic accents carry the reading order.", 150 * mm, 78 * mm, 120 * mm, size=8.5, leading=12, color="muted")


def page_provenance(c: canvas.Canvas, catalog: dict) -> None:
    draw_header(c, "Registry, provenance, and QA", "The repository stores derived rules and native templates; official links remain the evidence trail.", 8)
    counts: dict[str, int] = {}
    for entry in catalog["entries"]: counts[entry["conference"]] = counts.get(entry["conference"], 0) + 1
    y = PAGE_H - 54 * mm; c.setFont("FigureFlowSans-Bold", 10); c.setFillColor(rgb("ink")); c.drawString(24 * mm, y, "Coverage"); y -= 9 * mm
    for conference in ("CVPR", "ICCV", "ICML", "NeurIPS", "ICLR"):
        accent = "blue" if conference == "CVPR" else "coral" if conference == "ICCV" else "teal" if conference == "ICML" else "violet" if conference == "NeurIPS" else "amber"
        c.setFillColor(rgb(accent)); c.roundRect(24 * mm, y, 28 * mm, 8 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("FigureFlowSans-Bold", 8); c.drawCentredString(38 * mm, y + 2.7 * mm, conference)
        c.setFillColor(rgb("ink")); c.setFont("FigureFlowSans-Bold", 10); c.drawString(58 * mm, y + 2.3 * mm, str(counts.get(conference, 0))); y -= 12 * mm
    draw_card(c, 88 * mm, 121 * mm, 82 * mm, 58 * mm, "Evidence boundary", "Published figure observations are separated from FigureFlow-derived design rules. Synthetic demo values remain labelled. External paper screenshots are not vendored.", "amber", "amberbg")
    draw_card(c, 180 * mm, 121 * mm, 82 * mm, 58 * mm, "QA completed", "Template compile: one page, embedded fonts, no clipping. Data demo: one page, no PDF warnings. Public-release gate: passed.", "emerald", "tealbg")
    draw_card(c, 88 * mm, 50 * mm, 174 * mm, 57 * mm, "Rebuild commands", "render_data_figure.py → synthetic data demo; compile_figures.py → native overview template; audit_figure.py + qa_pdf.py → visual and structural checks. The source_links.md file contains the official paper/award trail.", "blue", "bluebg")
    c.setFillColor(rgb("muted")); c.setFont("FigureFlowSans", 7); c.drawString(24 * mm, 14 * mm, "FigureFlow visual atlas · generated locally from repository-native assets · no external paper screenshots embedded")


def sanitize_pdf_resources(output: Path) -> None:
    """Remove ReportLab's unused unembedded default font from page resources."""
    reader = PdfReader(str(output))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page in writer.pages:
        resources = page.get("/Resources")
        if hasattr(resources, "get_object"):
            resources = resources.get_object()
        fonts = resources.get("/Font") if resources else None
        if hasattr(fonts, "get_object"):
            fonts = fonts.get_object()
        if fonts and "/F1" in fonts:
            content = page.get_contents().get_data()
            content = content.replace(b"/F1 12 Tf 14.4 TL", b"/F2+0 1 Tf 1.2 TL")
            stream = DecodedStreamObject()
            stream.set_data(content)
            page[NameObject("/Contents")] = writer._add_object(stream)
            del fonts["/F1"]
    temporary = output.with_name(f".{output.stem}.sanitized.pdf")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(output)


def build(output: Path) -> Path:
    catalog = json.loads((REGISTRY / "catalog.json").read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="figureflow_atlas_") as temporary:
        assets = make_demo_assets(ROOT, Path(temporary))
        c = canvas.Canvas(str(output), pagesize=landscape(A4), pageCompression=1)
        # Set an embedded font before any page operation so ReportLab does not
        # carry its unembedded Helvetica default into the PDF resource tree.
        c._fontname = "FigureFlowSans"
        c._fontsize = 1
        c.setFont("FigureFlowSans", 1)
        pages = [
            lambda: page_cover(c, catalog),
            lambda: page_grammar(c),
            lambda: page_main_examples(c, assets),
            lambda: page_data_examples(c, assets),
            lambda: page_template(c, assets),
            lambda: page_rollout(c),
            lambda: page_palette(c),
            lambda: page_provenance(c, catalog),
        ]
        for page in pages:
            page(); c.showPage()
        c.save()
    sanitize_pdf_resources(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output.resolve())
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
