#!/usr/bin/env python3
"""Rebuild layered paper figures from a pinned, locally supplied proceedings PDF."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from pathlib import Path

import cairocffi as cairo
import cairosvg
import pymupdf as fitz

if __package__:
    from .gallery import write_gallery
    from .source_path import resolve_source_paths
    from .tikz_export import write_tikz
else:
    from gallery import write_gallery
    from source_path import resolve_source_paths
    from tikz_export import write_tikz

HERE = Path(__file__).resolve().parent
SPECS = HERE / "specs"
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)
QA_DPI = 240
PAPER_ORDER = ("videoworld", "janus", "epona", "graphmimic", "motus", "dynaview")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rectangle(box):
    if (
        not isinstance(box, (list, tuple))
        or len(box) != 4
        or any(type(n) not in (int, float) or not math.isfinite(n) for n in box)
    ):
        raise ValueError(f"invalid point-space box: {box!r}")
    r = fitz.Rect(*box)
    if r.is_empty:
        raise ValueError(f"empty point-space box: {box!r}")
    return r


def validate(s):
    if not re.fullmatch(r"[a-z0-9_]+", s["id"]) or not re.fullmatch(r"[0-9a-f]{64}", s["sha256"]):
        raise ValueError("case ID or pinned PDF digest invalid")
    if not s["url"].startswith("https://") or type(s["page"]) is not int or s["page"] < 1:
        raise ValueError("expected HTTPS edition and one-based page")
    if not all(s.get(k) for k in ("paper", "venue", "figure", "claim", "family", "palette", "limitations")):
        raise ValueError("incomplete provenance")
    frame = rectangle(s["box"])
    seen = set()
    for index, layer in enumerate(s["layers"]):
        kind = layer["kind"]
        key = layer.get("id", f"{kind}-{index}")
        if key in seen or not re.fullmatch(r"[A-Za-z0-9_.:-]+", key):
            raise ValueError(f"duplicate or invalid layer ID: {key}")
        seen.add(key)
        if kind == "asset":
            if rectangle(layer["box"]).get_area() > 0.94 * frame.get_area():
                raise ValueError("a whole-figure crop cannot be the candidate")
            if not layer.get("role"):
                raise ValueError("evidence tiles require a named role")
        elif kind not in {"path", "rect", "ellipse", "text"}:
            raise ValueError(f"unsupported layer: {kind}")
    has_raster = any(v["kind"] == "asset" for v in s["layers"])
    if not any(v["kind"] != "asset" for v in s["layers"]):
        raise ValueError("at least one native layer is required")
    if not has_raster and s.get("evidence_mode") != "native-vector-only":
        raise ValueError("missing evidence tiles; explicitly mark an all-vector original")


def sub(node, tag, **attrs):
    return ET.SubElement(node, f"{{{SVG}}}{tag}", {k: str(v) for k, v in attrs.items() if v is not None})


def strbox(b):
    return " ".join(f"{n:.7g}" for n in b)


def raw_tile(doc, xref):
    pix = fitz.Pixmap(doc, xref)
    kind, mask = doc.xref_get_key(xref, "SMask")
    if kind == "xref":
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        pix = fitz.Pixmap(pix, fitz.Pixmap(doc, int(mask.split()[0])))
    if pix.colorspace and pix.colorspace.n > 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix.tobytes("png")


def text_scale(layer):
    """Apply SVG textLength as a native transform, also supported by Cairo PDF."""
    font = layer.get("font", "sans-serif")
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
    ctx.select_font_face(
        font.split(",")[0].strip(" '"),
        cairo.FONT_SLANT_ITALIC if layer.get("style") == "italic" else cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD
        if str(layer.get("weight")).lower() in {"bold", "600", "700", "800", "900"}
        else cairo.FONT_WEIGHT_NORMAL,
    )
    ctx.set_font_size(layer["size"])
    width = ctx.text_extents(layer["text"])[4]
    return float(layer["length"]) / width if width > 0 else 1


def render(s, source, out, dpi=QA_DPI):
    validate(s)
    if digest(source.read_bytes()) != s["sha256"]:
        raise ValueError(f"{s['id']}: PDF hash does not match {s['url']}")
    frame = rectangle(s["box"])
    out.mkdir(parents=True, exist_ok=True)
    assets = out / "assets"
    assets.mkdir(exist_ok=True)
    root = ET.Element(
        f"{{{SVG}}}svg",
        {
            "width": f"{frame.width}pt",
            "height": f"{frame.height}pt",
            "viewBox": strbox([frame.x0, frame.y0, frame.width, frame.height]),
        },
    )
    sub(root, "title").text = f"{s['paper']}, {s['figure']} — source-assisted reconstruction"
    sub(root, "desc").text = s["claim"] + " | Published figure; not new experimental output. " + s["url"]
    defs = sub(root, "defs")
    for name, stops in s.get("gradients", {}).items():
        g = sub(defs, "linearGradient", id=name)
        for offset, color in stops:
            sub(g, "stop", offset=offset, **{"stop-color": color})
    sub(root, "rect", x=frame.x0, y=frame.y0, width=frame.width, height=frame.height, fill="white")
    evidence = []
    with fitz.open(source) as doc:
        p = doc[s["page"] - 1]
        if not p.rect.contains(frame):
            raise ValueError(f"figure box outside paper: {s['id']}")
        p.get_pixmap(clip=frame, dpi=dpi, alpha=False).save(out / "reference.png")
        layers = s["layers"]
        if any("source_seqno" in x for x in layers):
            layers = resolve_source_paths(p, layers)
        source_images = {}
        if any("xref" in a for a in layers):
            for im in p.get_image_info(xrefs=True):
                source_images.setdefault(im["xref"], []).append(fitz.Rect(im["bbox"]))
        with ExitStack() as stack:
            clean_page = None
            for i, a in enumerate(layers):
                kind = a["kind"]
                key = a.get("id", f"{kind}-{i}")
                dest = sub(root, "g", id=key)
                if a.get("clip"):
                    r = rectangle(a["clip"])
                    clip = sub(defs, "clipPath", id=f"clip-{i}", clipPathUnits="userSpaceOnUse")
                    sub(clip, "rect", x=r.x0, y=r.y0, width=r.width, height=r.height)
                    dest.set("clip-path", f"url(#clip-{i})")
                if a.get("transform"):
                    dest.set("transform", a["transform"])
                common = {}
                for src, tgt in (
                    ("opacity", "opacity"),
                    ("fill_opacity", "fill-opacity"),
                    ("fillOpacity", "fill-opacity"),
                    ("stroke_opacity", "stroke-opacity"),
                    ("strokeOpacity", "stroke-opacity"),
                    ("fill_rule", "fill-rule"),
                    ("rule", "fill-rule"),
                    ("dash", "stroke-dasharray"),
                    ("linecap", "stroke-linecap"),
                    ("linejoin", "stroke-linejoin"),
                ):
                    if src in a:
                        common[tgt] = " ".join(map(str, a[src])) if isinstance(a[src], list) else a[src]
                if kind == "asset":
                    b = rectangle(a["box"])
                    target = rectangle(a.get("dest", a["box"]))
                    if not p.rect.contains(b):
                        raise ValueError(f"tile outside paper: {key}")
                    if "xref" in a:
                        ref = int(a["xref"])
                        if not any(b.intersects(v) for v in source_images.get(ref, [])):
                            raise ValueError(
                                f"{key}: image object does not occur at its claimed page position"
                            )
                        data = raw_tile(doc, ref)
                    else:
                        if a.get("baseOnly") and clean_page is None:
                            clean = stack.enter_context(fitz.open())
                            clean.insert_pdf(doc, from_page=p.number, to_page=p.number)
                            clean_page = clean[0]
                            clean_page.add_redact_annot(clean_page.rect, fill=False)
                            clean_page.apply_redactions(images=0, graphics=2, text=0)
                        page = clean_page if a.get("baseOnly") else p
                        data = page.get_pixmap(clip=b, dpi=dpi, alpha=False).tobytes("png")
                    filename = f"assets/{key}.png"
                    (out / filename).write_bytes(data)
                    evidence.append(
                        {
                            "id": key,
                            "file": filename,
                            "role": a["role"],
                            "source_box_pt": a["box"],
                            "xref": a.get("xref"),
                            "images_only": bool(a.get("baseOnly")),
                            "sha256": digest(data),
                        }
                    )
                    sub(
                        dest,
                        "image",
                        x=target.x0,
                        y=target.y0,
                        width=target.width,
                        height=target.height,
                        preserveAspectRatio="none",
                        **{f"{{{XLINK}}}href": filename},
                        **common,
                    )
                elif kind == "text":
                    x, y = a["x"], a["y"]
                    node = sub(
                        dest,
                        "text",
                        x=x,
                        y=y,
                        fill=a.get("fill", "black"),
                        **{
                            "font-family": a.get("font", "sans-serif"),
                            "font-size": a["size"],
                            "font-weight": a.get("weight", "normal"),
                            "font-style": a.get("style", "normal"),
                            "text-anchor": a.get("anchor", "start"),
                            "{http://www.w3.org/XML/1998/namespace}space": "preserve",
                        },
                        **common,
                    )
                    node.text = a["text"]
                    transforms = []
                    if "rotate" in a:
                        transforms.append(f"rotate({a['rotate']} {x} {y})")
                    if a.get("length") and a["text"].strip():
                        transforms.append(f"translate({x} {y}) scale({text_scale(a)} 1) translate({-x} {-y})")
                    if transforms:
                        node.set("transform", " ".join(transforms))
                else:
                    keys = {
                        "rect": {"x": "x", "y": "y", "w": "width", "h": "height", "rx": "rx", "ry": "ry"},
                        "ellipse": {"cx": "cx", "cy": "cy", "rx": "rx", "ry": "ry"},
                        "path": {"d": "d"},
                    }[kind]
                    sub(
                        dest,
                        kind,
                        **{v: a[k] for k, v in keys.items() if k in a},
                        fill=a.get("fill", "none"),
                        stroke=a.get("stroke", "none"),
                        **{"stroke-width": a.get("sw", 1)},
                        **common,
                    )
    svg = out / "candidate.svg"
    ET.ElementTree(root).write(svg, encoding="utf-8", xml_declaration=True)
    write_tikz(s, layers, out)
    # Editable SVG links separate files. Embed only for portable PDF export.
    portable = copy.deepcopy(root)
    for img in portable.iter(f"{{{SVG}}}image"):
        href = f"{{{XLINK}}}href"
        img.set(
            href,
            "data:image/png;base64," + base64.b64encode((out / img.get(href)).read_bytes()).decode("ascii"),
        )
    pdf = out / "candidate.pdf"
    cairosvg.svg2pdf(bytestring=ET.tostring(portable), write_to=str(pdf))
    with fitz.open(pdf) as check:
        if (
            len(check) != 1
            or max(abs(check[0].rect.width - frame.width), abs(check[0].rect.height - frame.height)) >= 0.1
        ):
            raise ValueError("candidate PDF does not preserve the original figure dimensions")
        check[0].get_pixmap(dpi=dpi, alpha=False).save(out / "candidate.png")
    comparison([s], out.parent, out / "comparison.pdf")
    with fitz.open(out / "comparison.pdf") as cmp:
        cmp[0].get_pixmap(dpi=100, alpha=False).save(out / "comparison.png")
    write_json(
        out / "provenance.json",
        {
            "id": s["id"],
            "source": s["url"],
            "source_pdf_sha256": s["sha256"],
            "page": s["page"],
            "crop_pt": s["box"],
            "paper_width_pt": frame.width,
            "dpi": dpi,
            "spec_sha256": digest(json.dumps(s, sort_keys=True).encode()),
            "evidence_status": "published-figure",
            "assets": evidence,
            "native_layers": len(layers) - len(evidence),
            "limitations": s["limitations"],
            "outputs": {
                f: digest((out / f).read_bytes())
                for f in [
                    "reference.png",
                    "candidate.svg",
                    "candidate_tikz.tex",
                    "candidate.pdf",
                    "candidate.png",
                    "comparison.png",
                    "comparison.pdf",
                ]
            },
        },
    )


def compile_tikz(s, directory):
    """Compile optional TeX export without changing the canonical SVG proof."""
    with tempfile.TemporaryDirectory(prefix="figureflow-tex-") as job:
        result = subprocess.run(
            [
                "xelatex",
                "-no-shell-escape",
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-output-directory={job}",
                "candidate_tikz.tex",
            ],
            cwd=directory,
            capture_output=True,
            check=False,
            text=True,
            timeout=180,
        )
        if result.returncode:
            raise ValueError(f"{s['id']}: XeLaTeX failed\n{result.stdout[-2000:]}")
        log = (Path(job) / "candidate_tikz.log").read_text(errors="replace")
        if "Missing character:" in log or "Overfull \\hbox" in log:
            raise ValueError(f"{s['id']}: missing glyph or overflowing TeX text")
        pdf = Path(job) / "candidate_tikz.pdf"
        b = rectangle(s["box"])
        with fitz.open(pdf) as doc:
            if (
                len(doc) != 1
                or max(abs(doc[0].rect.width - b.width), abs(doc[0].rect.height - b.height)) > 0.1
            ):
                raise ValueError(f"{s['id']}: TeX figure has unexpected page size")
        shutil.copyfile(pdf, directory / pdf.name)
    metadata = directory / "provenance.json"
    report = json.loads(metadata.read_text())
    report["outputs"]["candidate_tikz.pdf"] = digest((directory / "candidate_tikz.pdf").read_bytes())
    write_json(metadata, report)


def comparison(specs, base, target, *, tikz=False):
    """One figure per page at native paper width, same scale and crop for both."""
    with fitz.open() as atlas:
        for s in specs:
            directory = base / s["id"]
            b = rectangle(s["box"])
            w, h = b.width, b.height
            margin, gap = 24, 18
            page = atlas.new_page(width=w * 2 + margin * 2 + gap, height=h + 117)
            page.insert_font(fontname="ReviewBody", fontbuffer=fitz.Font("helv").buffer)
            page.insert_font(fontname="ReviewBold", fontbuffer=fitz.Font("hebo").buffer)
            page.insert_text(
                (margin, 22), f"{s['paper']}   /   {s['figure']}", fontname="ReviewBold", fontsize=13
            )
            label_candidate = "RECONSTRUCTION  /  native TikZ" if tikz else "RECONSTRUCTION  /  layered SVG"
            for idx, label in enumerate(("ORIGINAL  /  published evidence", label_candidate)):
                x = margin + idx * (w + gap)
                page.insert_text((x, 45), label, fontname="ReviewBody", fontsize=8, color=(0.16, 0.31, 0.36))
                r = fitz.Rect(x, 54, x + w, 54 + h)
                if idx == 0:
                    page.insert_image(r, filename=str(directory / "reference.png"), keep_proportion=False)
                else:
                    with fitz.open(
                        directory / ("candidate_tikz.pdf" if tikz else "candidate.pdf")
                    ) as candidate:
                        page.show_pdf_page(r, candidate, 0)
            page.insert_text(
                (margin, h + 76),
                f"{s['venue']}   |   Source PDF page {s['page']}   |   Same scale: {w:.1f} pt per figure   |   Source-assisted, not rerun",
                fontname="ReviewBody",
                fontsize=8,
            )
            note = s["limitations"] if isinstance(s["limitations"], str) else " ".join(s["limitations"])
            note = note.translate(str.maketrans({"–": "-", "—": "-", "’": "'", "×": "x"}))
            available = page.insert_textbox(
                fitz.Rect(margin, h + 82, page.rect.width - margin, h + 116),
                note,
                fontname="ReviewBody",
                fontsize=7,
                color=(0.24, 0.27, 0.29),
            )
            if available < 0:
                raise ValueError(f"{s['id']}: attribution overflows the comparison page")
            page.insert_link(
                {
                    "kind": fitz.LINK_URI,
                    "from": fitz.Rect(margin, 4, page.rect.width - margin, 28),
                    "uri": s["url"],
                }
            )
        atlas.set_metadata(
            {
                "title": "FigureFlow | Published and rebuilt",
                "subject": "Attributed visual comparison; not new experiments",
            }
        )
        atlas.save(target, deflate=True, garbage=4)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--case")
    group.add_argument("--all", action="store_true")
    p.add_argument("--source-dir", type=Path, help="Directory of paper-ID.pdf files (one per paper)")
    p.add_argument("--output-dir", type=Path, default=HERE / "local")
    p.add_argument(
        "--compile-tikz",
        action="store_true",
        help="Also compile native TeX with XeLaTeX; --all builds a second comparison atlas",
    )
    args = p.parse_args()
    ranked = {paper: i for i, paper in enumerate(PAPER_ORDER)}
    cases = {
        f.stem: json.loads(f.read_text())
        for f in sorted(
            SPECS.glob("*.json"), key=lambda f: (ranked.get(f.stem.split("_fig")[0], 999), f.stem)
        )
    }
    for name, s in cases.items():
        validate(s)
        if s["id"] != name:
            raise ValueError(f"case name and ID disagree: {name}")
    if args.list:
        for s in cases.values():
            print(s["id"], "|", s["family"], "|", s["url"])
        return
    if args.case and args.case not in cases:
        p.error("unknown case; run --list")
    if not args.source_dir:
        p.error("supply --source-dir containing the pinned local PDFs")
    specs = [cases[args.case]] if args.case else list(cases.values())
    if not specs:
        p.error("no installed case specs")
    for s in specs:
        pdf = args.source_dir / (s["id"].split("_fig")[0] + ".pdf")
        render(s, pdf, args.output_dir / s["id"])
        if args.compile_tikz:
            compile_tikz(s, args.output_dir / s["id"])
        print(s["id"], "->", args.output_dir / s["id"] / "comparison.png", flush=True)
    if args.all:
        comparison(specs, args.output_dir, args.output_dir / "figureflow_comparisons.pdf")
        if args.compile_tikz:
            comparison(specs, args.output_dir, args.output_dir / "tikz_comparisons.pdf", tikz=True)
        write_gallery(specs, args.output_dir)


if __name__ == "__main__":
    main()
