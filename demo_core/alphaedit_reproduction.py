"""Offline AlphaEdit Figure 2 reconstruction from semantic vector primitives.

Exact-artwork mode preserves source geometry and outlined text. It intentionally
rejects changed data: use data_analysis for a new, quantitatively scaled chart.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import cairosvg
import numpy as np
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "alphaedit_figure2"
ATTRIBUTION = (
    "Adapted from Fang et al., AlphaEdit, ICLR 2025, Fig. 2; arXiv:2410.02355v4; CC BY 4.0. "
    "FigureFlow vector reconstruction, not a rerun of model experiments."
)
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_case(case_dir: Path = CASE) -> tuple[dict, list[dict]]:
    scene = json.loads((case_dir / "scene.json").read_text())
    with (case_dir / "data.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    bars = { (e["data"]["metric"], e["data"]["method"]): e["data"]
             for e in scene["elements"] if e.get("data") }
    keys = [(r["metric"], r["method"]) for r in rows]
    if len(keys) != 55 or len(set(keys)) != 55 or set(keys) != set(bars):
        raise ValueError("The faithful case requires all 55 audited metric/method pairs")
    for row in rows:
        original = bars[(row["metric"], row["method"])]
        if float(row["value"]) != original["value"] or row["label"] != original["label"]:
            raise ValueError("Changed data cannot reuse fixed source geometry; use data_analysis instead")
    elements = {element["id"]: element for element in scene["elements"]}
    numeric = scene.get("numeric_labels", [])
    if len(numeric) != 55:
        raise ValueError("Missing independent source numeric-label bindings")
    for binding in numeric:
        original = bars[(binding["metric"], binding["method"])]
        actual = "".join(elements[identity]["attrs"].get("data-text", "")
                         for identity in binding["glyph_ids"])
        if actual != binding["text"] or actual != original["label"]:
            raise ValueError("Numeric vector glyphs do not match the audited labels")
    return scene, rows


def compose_svg(scene: dict, rows: list[dict]) -> str:
    """Rebuild an SVG using vector primitives, never embed the source PDF/PNG."""
    root = ET.Element(f"{{{SVG}}}svg", {
        "width": f"{scene['width_pt']}pt", "height": f"{scene['height_pt']}pt",
        "viewBox": f"0 0 {scene['width_pt']} {scene['height_pt']}",
        "role": "img", "aria-labelledby": "figure-title figure-description",
    })
    ET.SubElement(root, "title", id="figure-title").text = "AlphaEdit Figure 2 — faithful reconstruction"
    ET.SubElement(root, "desc", id="figure-description").text = ATTRIBUTION
    ET.SubElement(root, "metadata").text = json.dumps({
        "evidence_status": "published-figure", "attribution": ATTRIBUTION,
        "source": "https://arxiv.org/abs/2410.02355v4",
        "data": rows,
    }, ensure_ascii=False)
    defs = ET.SubElement(root, "defs")
    for identity, outline in scene["glyph_outlines"].items():
        ET.SubElement(defs, "path", id=identity, d=outline)
    for element in scene["elements"]:
        attrs = {**element["attrs"], "id": element["id"]}
        if element.get("data"):
            data = element["data"]
            attrs.update({"data-metric": data["metric"], "data-method": data["method"],
                          "data-value": str(data["value"]), "aria-label": f"{data['method']}: {data['label']}"})
        if element["tag"] == "use":
            # Materialize every glyph as its own path: no system font or external resource required.
            attrs["d"] = scene["glyph_outlines"][attrs.pop("href").removeprefix("#")]
            node = ET.SubElement(root, "path", attrs)
        else:
            node = ET.SubElement(root, "path", attrs)
        if element.get("data"):
            ET.SubElement(node, "title").text = (
                f"{element['data']['metric']} / {element['data']['method']}: {element['data']['label']}"
            )
    return ET.tostring(root, encoding="unicode")


def raster_pdf(pdf: Path, png: Path, dpi: int = 240) -> str:
    """Use one rasterizer for both reference and reconstruction; no silent mismatch."""
    poppler = shutil.which("pdftoppm")
    if poppler:
        subprocess.run([poppler, "-cropbox", "-f", "1", "-l", "1", "-singlefile", "-r", str(dpi),
                        "-png", str(pdf), str(png.with_suffix(""))], check=True, capture_output=True)
        return "Poppler pdftoppm"
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Install Poppler for comparison, or optional PyMuPDF") from exc
    with fitz.open(pdf) as doc:
        doc[0].get_pixmap(dpi=dpi, alpha=False).save(png)
    return "PyMuPDF " + fitz.VersionBind


def compare_images(reference: Path, reproduction: Path, output: Path) -> dict:
    with Image.open(reference) as image:
        ref = np.asarray(image.convert("RGB"), dtype=np.int16)
    with Image.open(reproduction) as image:
        rep = np.asarray(image.convert("RGB"), dtype=np.int16)
    if ref.shape != rep.shape:
        raise ValueError(f"Comparison requires identical sizes: {ref.shape} != {rep.shape}")
    delta = np.abs(ref - rep)
    foreground = (ref.min(axis=2) < 245) | (rep.min(axis=2) < 245)
    metrics = {
        "size_px": [int(ref.shape[1]), int(ref.shape[0])],
        "mean_absolute_channel_error_0_255": float(delta.mean()),
        "foreground_mean_absolute_channel_error_0_255": float(delta[foreground].mean()),
        "channel_error_threshold_0_255": 8,
        "pixels_all_channel_error_le_threshold_percent": float((delta.max(axis=2) <= 8).mean() * 100),
        "exact_pixel_match_percent": float((delta.max(axis=2) == 0).mean() * 100),
        "note": "No resizing, alignment, or blank-margin padding. Rasterization/font-hinting differences remain.",
    }
    thumb_width = 700
    height = round(ref.shape[0] * thumb_width / ref.shape[1])
    gallery = Image.new("RGB", (thumb_width * 3 + 64, height + 110), "white")
    drawer = ImageDraw.Draw(gallery)
    for index, (pixels, title) in enumerate([
        (ref, "Official Figure 2"), (rep, "FigureFlow reconstruction"),
        (255 - np.clip(delta * 6, 0, 255), "Difference (6x; white = identical)"),
    ]):
        x = 16 + index * (thumb_width + 16)
        drawer.text((x, 15), title, fill="#253047")
        image = Image.fromarray(pixels.astype(np.uint8)).resize((thumb_width, height), Image.Resampling.LANCZOS)
        gallery.paste(image, (x, 45))
    drawer.text((16, height + 67), "Fang et al., AlphaEdit, ICLR 2025 | arXiv:2410.02355v4 | CC BY 4.0", fill="#444444")
    gallery.save(output)
    return metrics


def run_reproduction(output_dir: Path, *, case_dir: Path = CASE, dpi: int = 240) -> dict[str, str]:
    output_dir = Path(output_dir).resolve()
    if not 72 <= dpi <= 600:
        raise ValueError("DPI must be between 72 and 600")
    scene, rows = load_case(case_dir)
    reference = case_dir / "reference" / "intro_part2.pdf"
    if sha256(reference) != scene["source_sha256"]:
        raise ValueError("The official reference PDF checksum is invalid")
    if output_dir == case_dir.resolve() or case_dir.resolve() in output_dir.parents:
        raise ValueError("Use a separate output directory, never the source case directory")
    copied_names = ("data.csv", "source_audit.json", "SOURCES.md", "scene.json", "PROMPTS.md")
    created_names = (
        "alphaedit_figure2.svg", "alphaedit_figure2.pdf", "alphaedit_figure2.png",
        "reference.png", "comparison.png", "report.json", "manifest.json", "reproduction.zip",
        *copied_names,
    )
    for name in created_names:
        if (output_dir / name).is_symlink():
            raise ValueError("Refusing a symbolic-link output target")
    output_dir.mkdir(parents=True, exist_ok=True)
    svg = output_dir / "alphaedit_figure2.svg"
    pdf = output_dir / "alphaedit_figure2.pdf"
    png = output_dir / "alphaedit_figure2.png"
    svg.write_text(compose_svg(scene, rows), encoding="utf-8")
    pdf_bytes = cairosvg.svg2pdf(bytestring=svg.read_bytes())
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes)))
    writer.add_metadata({"/Title": "AlphaEdit Figure 2 — FigureFlow reconstruction",
                         "/Author": "Fang et al. (source); FigureFlow (reconstruction)",
                         "/Subject": ATTRIBUTION,
                         "/Keywords": "published-figure; CC BY 4.0; not an experimental rerun"})
    writer.add_attachment("data.csv", (case_dir / "data.csv").read_bytes())
    writer.add_attachment("SOURCES.md", (case_dir / "SOURCES.md").read_bytes())
    writer.write(pdf)
    rasterizer = raster_pdf(pdf, png, dpi)
    reference_png = output_dir / "reference.png"
    if raster_pdf(reference, reference_png, dpi) != rasterizer:
        raise RuntimeError("Rasterizer changed during the comparison")
    comparison = output_dir / "comparison.png"
    metrics = compare_images(reference_png, png, comparison)
    audit = json.loads((case_dir / "source_audit.json").read_text())
    report = output_dir / "report.json"
    report.write_text(json.dumps({
        "mode": "faithful-vector-reconstruction", "evidence_status": "published-figure",
        "model_experiments_rerun": False, "model_calls": 0,
        "counts": scene["counts"], "rasterizer": rasterizer, "dpi": dpi,
        "fidelity": metrics, "source_discrepancies": audit["substantive_discrepancies"],
        "boundary": "Source-specific geometry replay is separate from data-driven plotting. "
                    "Artist-adjusted lengths and tiny original labels are preserved, not endorsed.",
        "attribution": ATTRIBUTION,
    }, ensure_ascii=False, indent=2) + "\n")
    for name in copied_names:
        shutil.copyfile(case_dir / name, output_dir / name)
    manifest = output_dir / "manifest.json"
    manifest.write_text(json.dumps({
        "schema": "figureflow.reproduction.v1", "case": "alphaedit-figure2",
        "evidence_status": "published-figure", "attribution": ATTRIBUTION,
        "license": "CC BY 4.0 (source artwork); MIT (FigureFlow code)",
        "source_sha256": scene["source_sha256"],
        "artifacts": {name: sha256(output_dir / name) for name in created_names
                      if name not in {"manifest.json", "reproduction.zip"}},
    }, ensure_ascii=False, indent=2) + "\n")
    bundle = output_dir / "reproduction.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in created_names:
            if name != bundle.name:
                archive.write(output_dir / name, "output/" + name)
        # A portable, runnable mini-checkout, not a folder scan that may leak unrelated files.
        replay_files = [
            "demo_core/__init__.py", "demo_core/alphaedit_reproduction.py", "demo_core/data_analysis.py",
            "scripts/extract_alphaedit_scene.py", "requirements-reproduction.txt",
            "cases/alphaedit_figure2/README.md", "cases/alphaedit_figure2/reference/intro_part2.pdf",
            *["cases/alphaedit_figure2/" + name for name in copied_names],
        ]
        for relative in replay_files:
            if (ROOT / relative).is_file():
                archive.write(ROOT / relative, "replay/" + relative)
        archive.writestr("REPLAY.txt", "From replay/:\npython -m pip install -r requirements-reproduction.txt\n"
                          "Install Poppler (pdftoppm), then:\n"
                          "python -m demo_core.alphaedit_reproduction --output-dir ../rebuilt\n"
                          "Source artwork: Fang et al., AlphaEdit, ICLR 2025; CC BY 4.0.\n")
    return {"png": str(png), "pdf": str(pdf), "svg": str(svg), "comparison": str(comparison),
            "report": str(report), "manifest": str(manifest), "data": str(output_dir / "data.csv"),
            "zip": str(bundle)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "demo/output/alphaedit_figure2")
    parser.add_argument("--dpi", type=int, default=240)
    args = parser.parse_args()
    print(json.dumps(run_reproduction(args.output_dir, dpi=args.dpi), indent=2))


if __name__ == "__main__":
    main()
