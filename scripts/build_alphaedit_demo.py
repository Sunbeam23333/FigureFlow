"""Build the three AlphaEdit figure modes and a vector-only A4 paper preview.

Run from any working directory: python /path/to/scripts/build_alphaedit_demo.py.
The preview merges the generated PDF pages, never screenshots of the charts.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_CACHE = Path(tempfile.gettempdir()) / "figureflow-demo-cache"
_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_CACHE / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE / "xdg"))

import cairosvg
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pypdf import PdfReader, PdfWriter

from demo_core.alphaedit_reproduction import ATTRIBUTION, CASE, raster_pdf, run_reproduction
from demo_core.data_analysis import render_annular_chart, render_small_multiples


PAGE_WIDTH = 595.2756
PAGE_HEIGHT = 841.8898
COLUMN_WIDTH = 234.0  # 3.25 inches, fixed rather than content-dependent sizing.
PAGE_MARGIN = 45.0
LEFT_X = PAGE_MARGIN
RIGHT_X = PAGE_WIDTH - PAGE_MARGIN - COLUMN_WIDTH
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _page_background() -> str:
    root = ET.Element(f"{{{SVG_NS}}}svg", {
        "width": f"{PAGE_WIDTH}pt", "height": f"{PAGE_HEIGHT}pt",
        "viewBox": f"0 0 {PAGE_WIDTH} {PAGE_HEIGHT}",
    })
    ET.SubElement(root, "rect", width=str(PAGE_WIDTH), height=str(PAGE_HEIGHT), fill="white")

    def text(x: float, y: float, value: str, *, size: float = 9, color: str = "#49505E",
             weight: str = "normal") -> None:
        node = ET.SubElement(root, "text", {
            "x": str(x), "y": str(y), "font-family": "DejaVu Sans, sans-serif",
            "font-size": str(size), "font-weight": weight, "fill": color,
        })
        node.text = value

    def rule(y: float) -> None:
        ET.SubElement(root, "line", {
            "x1": str(PAGE_MARGIN), "x2": str(PAGE_WIDTH - PAGE_MARGIN),
            "y1": str(y), "y2": str(y), "stroke": "#E1E3E9", "stroke-width": "0.7",
        })

    text(LEFT_X, 43, "FIGUREFLOW / REPRODUCIBLE PAPER FIGURES", size=8, color="#6B63A3", weight="bold")
    text(LEFT_X, 69, "AlphaEdit Figure 2: two rendering modes", size=18, color="#222635", weight="bold")
    text(LEFT_X, 89, "LLaMA3 (8B)  |  11 metrics  |  5 methods  |  55 published display values", size=9)
    rule(106)

    text(LEFT_X, 130, "A. Faithful source reconstruction", size=10.5, color="#333047", weight="bold")
    text(RIGHT_X, 130, "B. Data-driven annular chart", size=10.5, color="#333047", weight="bold")
    text(LEFT_X, 146, "Original vector geometry and glyph outlines", size=8.4)
    text(RIGHT_X, 146, "Recalculated radii from the same CSV values", size=8.4)

    left_lines = [
        "Preserves the original contours, rotated glyphs,",
        "colors and manually adjusted bar lengths.",
        "Changing the CSV requires data-driven mode.",
    ]
    right_lines = [
        "Bar lengths are computed from the CSV.",
        "Each metric uses its own maximum as scale.",
        "Zero values have zero radial length.",
    ]
    for index, (left, right) in enumerate(zip(left_lines, right_lines)):
        text(LEFT_X, 465 + index * 14, left, size=8.2)
        text(RIGHT_X, 465 + index * 14, right, size=8.2)

    rule(515)
    text(LEFT_X, 542, "Evidence and interpretation", size=11, color="#333047", weight="bold")
    evidence = [
        "Published-figure values, not a model rerun. No model or image-generation API is called.",
        "Four labels differ materially from Table 1; the source audit preserves these conflicts.",
        "Compare methods within each metric. Different metrics use different units and scales.",
        "No cross-metric aggregate, uncertainty estimate or statistical significance is inferred.",
    ]
    for index, line in enumerate(evidence):
        text(LEFT_X, 563 + index * 15, line)

    text(LEFT_X, 643, "Paper-width inspection: 3.25 inches per panel", size=11, color="#333047", weight="bold")
    limitations = [
        "The source reconstruction intentionally preserves tiny original labels for 1:1 fidelity.",
        "This preview does not approve the source artwork's minimum type size for a new paper.",
        "Read exact values in the full-size vector PDFs or the conventional analysis panels.",
        "The analysis/ folder contains separate per-metric bar charts in their original units.",
    ]
    for index, line in enumerate(limitations):
        text(LEFT_X, 664 + index * 15, line)

    rule(747)
    text(LEFT_X, 770, "Source: Fang et al., AlphaEdit, ICLR 2025, Figure 2. arXiv:2410.02355v4.", size=8.3)
    text(LEFT_X, 785, "CC BY 4.0. FigureFlow rebuilds the vector artwork and adds an independent data renderer.", size=8.3)
    text(LEFT_X, 805, "Source and conflict details accompany every mode. No experimental rerun is claimed.", size=8)
    return ET.tostring(root, encoding="unicode")


def _merge_pdf_panel(target, source_path: Path, *, x: float, top: float, width: float) -> dict:
    reader = PdfReader(source_path)
    if len(reader.pages) != 1:
        raise ValueError(f"The paper preview requires a one-page chart: {source_path.name}")
    source = reader.pages[0]
    box = source.cropbox
    source_width, source_height = float(box.width), float(box.height)
    scale = width / source_width
    height = source_height * scale
    if top + height > 446:
        raise ValueError(f"Chart would overlap its paper caption: {source_path.name}")
    transform = (
        scale, 0, 0, scale,
        x - float(box.left) * scale,
        PAGE_HEIGHT - top - height - float(box.bottom) * scale,
    )
    target.merge_transformed_page(source, transform, over=True, expand=False)
    return {"include_width_pt": width, "include_width_inches": width / 72,
            "height_pt": height, "left_pt": x, "top_pt": top, "vector_page_merge": True}


def _paper_preview(exact_pdf: Path, data_pdf: Path, output: Path) -> dict[str, Path | dict]:
    svg_path = output / "paper_preview_layout.svg"
    pdf_path = output / "paper_preview.pdf"
    png_path = output / "paper_preview.png"
    svg_path.write_text(_page_background(), encoding="utf-8")
    background = PdfReader(io.BytesIO(cairosvg.svg2pdf(bytestring=svg_path.read_bytes())))
    page = background.pages[0]
    placements = {
        "source_reconstruction": _merge_pdf_panel(page, exact_pdf, x=LEFT_X, top=169, width=COLUMN_WIDTH),
        "data_driven": _merge_pdf_panel(page, data_pdf, x=RIGHT_X, top=169, width=COLUMN_WIDTH),
    }
    writer = PdfWriter()
    writer.add_page(page)
    writer.add_metadata({
        "/Title": "FigureFlow AlphaEdit Figure 2 - vector reconstruction and data-driven plotting",
        "/Author": "FigureFlow; original artwork by Fang et al.",
        "/Subject": ATTRIBUTION,
        "/Keywords": "published-figure; CC BY 4.0; not a model rerun; vector-only paper preview",
    })
    writer.write(pdf_path)
    raster_pdf(pdf_path, png_path, dpi=240)
    return {"pdf": pdf_path, "png": png_path, "layout_svg": svg_path, "placements": placements}


def _gallery(entries: list[tuple[Path, str, str]], target: Path) -> None:
    from matplotlib import font_manager

    regular = font_manager.findfont("DejaVu Sans")
    bold = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight="bold"))
    title_font = ImageFont.truetype(bold, 22)
    note_font = ImageFont.truetype(regular, 15)
    cell_width, cell_height, margin = 760, 1000, 28
    gallery = Image.new("RGB", (2 * cell_width + 3 * margin, 2 * cell_height + 3 * margin), "#F0F1F5")
    draw = ImageDraw.Draw(gallery)
    for index, (path, title, note) in enumerate(entries):
        left = margin + (index % 2) * (cell_width + margin)
        top = margin + (index // 2) * (cell_height + margin)
        draw.rounded_rectangle((left, top, left + cell_width, top + cell_height), radius=12, fill="white")
        draw.text((left + 24, top + 21), title, font=title_font, fill="#303043")
        draw.text((left + 24, top + 56), note, font=note_font, fill="#74717F")
        with Image.open(path) as image:
            thumb = ImageOps.contain(image.convert("RGB"), (cell_width - 44, cell_height - 116),
                                    Image.Resampling.LANCZOS)
        gallery.paste(thumb, (left + (cell_width - thumb.width) // 2, top + 91))
    gallery.save(target)


def _relative_outputs(outputs: dict[str, str], root: Path) -> dict[str, str]:
    return {key: Path(value).resolve().relative_to(root).as_posix() for key, value in outputs.items()}


def build_demo(output_dir: Path) -> dict:
    output = Path(output_dir).resolve()
    if output == CASE.resolve() or CASE.resolve() in output.parents:
        raise ValueError("Choose a demo output directory outside the source case")
    generated_names = ("paper_preview_layout.svg", "paper_preview.pdf", "paper_preview.png",
                       "gallery.png", "demo_manifest.json")
    if any((output / name).is_symlink() for name in generated_names):
        raise ValueError("Refusing a symbolic-link preview target")
    output.mkdir(parents=True, exist_ok=True)
    csv_path = CASE / "data.csv"
    exact = run_reproduction(output / "exact")
    data = render_annular_chart(
        csv_path, output / "data", title="AlphaEdit", subtitle="LLaMA3 (8B)\nPublished Figure 2 values",
        focus_method="AlphaEdit",
    )
    analysis = render_small_multiples(
        csv_path, output / "analysis", title="AlphaEdit Figure 2 - published values", focus_method="AlphaEdit",
    )
    preview = _paper_preview(Path(exact["pdf"]), Path(data["pdf"]), output)
    gallery = output / "gallery.png"
    _gallery([
        (Path(exact["png"]), "01 / Faithful source reconstruction", "Rebuilt vectors; original glyphs and manual geometry"),
        (Path(data["png"]), "02 / Data-driven annular chart", "New radii from CSV; independent metric scales"),
        (Path(analysis["png"]), "03 / Conventional analysis panels", "Original units; method rankings within each metric"),
        (Path(preview["png"]), "04 / Vector paper-width inspection", "Native PDF panels; 3.25 inches per column"),
    ], gallery)
    groups = {"exact": _relative_outputs(exact, output), "data": _relative_outputs(data, output),
              "analysis": _relative_outputs(analysis, output),
              "preview": {key: Path(preview[key]).relative_to(output).as_posix()
                          for key in ("pdf", "png", "layout_svg")}, "gallery": "gallery.png"}

    # Explicit inventories from each renderer include source copies without
    # sweeping unrelated files that happen to be in an existing output folder.
    produced = {Path(path).resolve() for group in (exact, data, analysis) for path in group.values()}
    produced.update(Path(preview[key]) for key in ("pdf", "png", "layout_svg"))
    produced.add(gallery)
    exact_manifest = json.loads(Path(exact["manifest"]).read_text(encoding="utf-8"))
    produced.update(output / "exact" / name for name in exact_manifest["artifacts"])
    for group, directory in ((data, "data"), (analysis, "analysis")):
        manifest = json.loads(Path(group["manifest"]).read_text(encoding="utf-8"))
        produced.update(output / directory / record["filename"] for record in manifest["outputs"].values())
    artifacts = []
    for path in sorted(produced):
        relative = path.resolve().relative_to(output).as_posix()
        artifacts.append({"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)})
    manifest = {
        "schema": "figureflow.alphaedit-demo.v1", "evidence_status": "published-figure",
        "model_calls": 0, "model_experiments_rerun": False,
        "source": {"csv": "cases/alphaedit_figure2/data.csv", "csv_sha256": _sha256(csv_path),
                   "paper": "https://arxiv.org/abs/2410.02355v4", "attribution": ATTRIBUTION},
        "outputs": groups, "artifacts": artifacts,
        "paper_preview": {"page_size_pt": [PAGE_WIDTH, PAGE_HEIGHT], "pages": 1,
                          "render_dpi": 240, "panels": preview["placements"],
                          "chart_embedding": "native PDF vector pages; no chart screenshots"},
        "limitations": [
            "Exact mode reconstructs source artwork, not original plotting code or model experiments.",
            "Data-driven mode recalculates radii and independently scales each metric.",
            "Four figure labels conflict with Table 1; all modes retain Figure 2's displayed values.",
            "The source's tiny labels are preserved; this comparison is not a minimum-font-size approval.",
            "No cross-metric aggregate or statistical significance is inferred.",
        ],
    }
    (output / "demo_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "demo/output/alphaedit_demo")
    args = parser.parse_args()
    manifest = build_demo(args.output_dir)
    print(json.dumps({"manifest": "demo_manifest.json", "outputs": manifest["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
