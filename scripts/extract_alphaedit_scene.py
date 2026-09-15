"""One-time, auditable vector digitization of the official AlphaEdit Figure 2 PDF.

This is NOT the authors' plotting source. It preserves their Illustrator geometry.
Run from the repository root; the normal reproduction does not need this tool.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

EXPECTED_SHA256 = "a3f9f7293ecd91dc35d04d47ee17693ae87bfa0334cea169f06c990d2fd62921"
NS = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
COLORS = {
    "#645ac6": "AlphaEdit", "#c3dec3": "RECT", "#ffdcc7": "PRUNE",
    "#a3b5d6": "MEMIT", "#dea991": "ROME",
}
METRICS = [
    "Efficacy", "SST", "CoLA", "RTE", "Specificity*", "Generalization*",
    "Efficacy*", "Consistency", "Fluency", "Specificity", "Generalization",
]
CHART_CENTER = (217.8, 222.0)


def _polar_angle(bounds: list[float]) -> float:
    return (math.degrees(math.atan2(
        (bounds[1] + bounds[3]) / 2 - CHART_CENTER[1],
        (bounds[0] + bounds[2]) / 2 - CHART_CENTER[0],
    )) + 90) % 360


def _glyph_origin(element: dict) -> tuple[float, float]:
    transform = element["attrs"].get("transform", "")
    match = re.fullmatch(r"matrix\(([^)]+)\)", transform)
    if not match:
        raise ValueError("Numeric glyph has no explicit matrix origin")
    values = [float(value) for value in re.split(r"[,\s]+", match.group(1).strip())]
    if len(values) != 6 or not all(math.isfinite(value) for value in values):
        raise ValueError("Numeric glyph matrix is invalid")
    return values[4], values[5]


def bind_numeric_labels(page, elements: list[dict], ordered_bars: list[dict]) -> list[dict]:
    """Bind independently extracted PDF white text to its actual SVG glyphs and bar."""
    spans = [
        span
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["color"] == 0xFFFFFF
    ]
    if len(spans) != 55 or any(not re.fullmatch(r"\d+(?:\.\d+)?", span["text"]) for span in spans):
        raise ValueError("Expected exactly 55 numeric white-text spans in the source PDF")
    glyphs = [element for element in elements if element["tag"] == "use"]
    white = [element for element in glyphs if element["attrs"].get("fill") == "#ffffff"]
    for glyph in glyphs:
        glyph["role"] = "numeric-label" if glyph["attrs"].get("fill") == "#ffffff" else "annotation"
    bindings = []
    consumed = 0
    for span in spans:
        # Both PDF text spans and SVG uses preserve source paint order. Check the
        # initial baseline origin independently before consuming the character run.
        run = white[consumed:consumed + len(span["text"])]
        if len(run) != len(span["text"]):
            raise ValueError("PDF numeric spans and white SVG glyph counts disagree")
        if math.dist(_glyph_origin(run[0]), span["origin"]) > 0.001:
            raise ValueError("PDF numeric span origin does not match its first SVG glyph")
        actual = "".join(glyph["attrs"].get("data-text", "") for glyph in run)
        if actual != span["text"]:
            raise ValueError("SVG numeric glyph text disagrees with independent PDF text extraction")
        bindings.append({
            "text": actual,
            "bounds": list(span["bbox"]),
            "origin": list(span["origin"]),
            "glyph_ids": [glyph["id"] for glyph in run],
        })
        consumed += len(run)
    if consumed != len(white):
        raise ValueError("Unassigned white numeric glyphs remain in the source artwork")
    bindings.sort(key=lambda binding: _polar_angle(binding["bounds"]))
    if len(bindings) != len(ordered_bars):
        raise ValueError("The numeric labels and data bars are not one-to-one")
    by_id = {glyph["id"]: glyph for glyph in glyphs}
    for binding, bar in zip(bindings, ordered_bars):
        if binding["text"] != bar["label"] or float(binding["text"]) != bar["value"]:
            raise ValueError(
                f"Source numeric label disagrees with CSV: {bar['metric']} / {bar['method']}"
            )
        binding.update({"metric": bar["metric"], "method": bar["method"]})
        for identity in binding["glyph_ids"]:
            by_id[identity]["attrs"]["data-label-key"] = f"{bar['metric']}/{bar['method']}"
    return bindings


def extract(pdf: Path, case_dir: Path) -> dict:
    import fitz  # Optional extraction dependency; not required for ordinary replay.

    if hashlib.sha256(pdf.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Source hash differs from the audited arXiv v4 Figure 2 PDF")
    with (case_dir / "data.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_key = {(r["metric"], r["method"]): r for r in rows}
    if len(rows) != 55 or len(by_key) != 55:
        raise ValueError("The source case needs 55 unique metric/method CSV rows")
    doc = fitz.open(pdf)
    page = doc[0]
    root = ET.fromstring(page.get_svg_image(text_as_path=True))
    definitions = {
        node.attrib["id"]: node.attrib["d"]
        for node in root.find(NS + "defs") if node.tag == NS + "path"
    }
    # Every source group has only clipping/layer attributes, never an inherited transform.
    for group in root.iter(NS + "g"):
        if any(k in group.attrib for k in ("transform", "opacity", "fill", "stroke")):
            raise ValueError("Unexpected inherited styling; update the extractor explicitly")
    drawings = page.get_drawings()
    bars = []
    for index, drawing in enumerate(drawings):
        if drawing["fill"] is None or drawing["rect"].y0 > 470:
            continue
        rect = drawing["rect"]
        angle = _polar_angle(list(rect))
        color = "#" + "".join(f"{round(c * 255):02x}" for c in drawing["fill"])
        bars.append((angle, index, COLORS[color]))
    if len(bars) != 55:
        raise ValueError("Expected exactly 55 data bars")
    bar_map = {}
    for ordinal, (_, index, method) in enumerate(sorted(bars)):
        metric = METRICS[ordinal // 5]
        if method != ["ROME", "MEMIT", "PRUNE", "RECT", "AlphaEdit"][ordinal % 5]:
            raise ValueError("Unexpected method order")
        row = by_key[(metric, method)]
        bar_map[index] = {
            "metric": metric, "method": method, "label": row["label"],
            "value": float(row["value"]), "bounds": list(drawings[index]["rect"]),
        }
    elements = []
    path_index = 0
    glyph_index = 0
    for group in root:
        if group.tag != NS + "g":
            continue
        for node in group.iter():
            tag = node.tag.removeprefix(NS)
            if tag not in {"path", "use"}:
                continue
            attrs = dict(node.attrib)
            if XLINK in attrs:
                attrs["href"] = attrs.pop(XLINK)
            if tag == "path":
                semantic = bar_map.get(path_index)
                identity = f"path-{path_index:03d}"
                if semantic:
                    slug = re.sub(r"[^a-z0-9]+", "-", semantic["metric"].lower()).strip("-")
                    if "*" in semantic["metric"]:
                        slug += "-zsre"
                    identity = f"bar-{slug}-{semantic['method'].lower()}"
                elements.append({"id": identity, "tag": tag, "attrs": attrs, "data": semantic})
                path_index += 1
            else:
                elements.append({"id": f"glyph-{glyph_index:03d}", "tag": tag, "attrs": attrs})
                glyph_index += 1
    if path_index != len(drawings):
        raise ValueError("SVG and PDF drawing inventories disagree")
    numeric_labels = bind_numeric_labels(page, elements, list(bar_map.values()))
    numeric_glyph_count = sum(len(label["glyph_ids"]) for label in numeric_labels)
    doc.close()
    result = {
        "schema": "figureflow.vector-reconstruction.v1",
        "source_sha256": EXPECTED_SHA256,
        "source_license": "CC BY 4.0",
        "width_pt": float(root.attrib["width"]), "height_pt": float(root.attrib["height"]),
        "glyph_outlines": definitions,
        "elements": elements,
        "numeric_labels": numeric_labels,
        "counts": {
            "bars": len(bars), "paths": path_index, "glyphs": glyph_index,
            "numeric_labels": len(numeric_labels), "numeric_glyphs": numeric_glyph_count,
            "annotation_glyphs": glyph_index - numeric_glyph_count,
        },
        "notes": [
            "Source-specific artistic vector reconstruction, not inferred value-to-radius scaling.",
            "Glyph outlines preserve typeset artwork without bundling font software.",
            "All 55 CSV labels are independently checked against PDF white-text spans and 198 SVG glyphs.",
            "Numeric glyph binding checks source paint order, span origins and clockwise bar association.",
            "No raw experiments were rerun.",
        ],
        "extractor": {"tool": "PyMuPDF", "version": fitz.VersionBind},
    }
    (case_dir / "scene.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--case-dir", type=Path, default=Path("cases/alphaedit_figure2"))
    args = parser.parse_args()
    print(json.dumps(extract(args.pdf, args.case_dir)["counts"]))
