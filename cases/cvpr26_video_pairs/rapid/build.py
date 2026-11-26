"""Rebuild RAPID Fig. 1 from 15 isolated frames and 46 individually placed words.

The PDF has a single JPEG; there are no source fonts, vector labels or timecodes.
Run with --source PDF --out DIR; recompose a different case with --template.
"""

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

import contourpy
import numpy as np
import pymupdf as pdf
from PIL import Image

RECIPE = Path(__file__).with_name("recipe.json")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rgb(value):
    return tuple(bytes.fromhex(value.lstrip("#")))


def ink_words(pixels, line):
    """Detect inter-word whitespace in the printed JPEG, not equal-width slots."""
    y0, y1 = line["text_y"]
    mask = pixels[y0:y1].min(2) < 122
    used = np.flatnonzero(mask.any(0))
    require(len(used) > 0, "no ink in " + line["id"])
    groups = np.split(used, np.flatnonzero(np.diff(used) > 9) + 1)
    tokens = line["text"].split()
    require(len(groups) == len(tokens), f"{line['id']}: word inventory differs")
    for i, (cols, token) in enumerate(zip(groups, tokens)):
        x0, x1 = int(cols[0]), int(cols[-1]) + 1
        ys = np.flatnonzero(mask[:, x0:x1].any(1))
        bounds = [x0, y0 + int(ys[0]), x1, y0 + int(ys[-1]) + 1]
        yield {
            "id": f"{line['id']}-{i:02d}", "text": token, "ink_box_px": bounds,
            "ink": line["accent"] if i >= line.get("accent_word", len(tokens)) else "ink"
        }


def build_layout(source_doc, recipe, out):
    require(digest(Path(source_doc.name).read_bytes()) == recipe["sha256"], "source PDF SHA-256 mismatch")
    page = source_doc[recipe["page_number"] - 1]
    ref = next(i for i in page.get_image_info(xrefs=True) if i["xref"] == recipe["image_xref"])
    require(np.max(np.abs(np.array(ref["bbox"]) - recipe["page_bbox_pt"])) < .001, "different figure bounds")
    require([ref["width"], ref["height"]] == recipe["size_px"], "different figure resolution")
    table = source_doc[6].get_text()
    for row in recipe["rows"]:
        t = row["table1"]
        # Match the exact values in order, with the original row name and no other intervening method.
        score = re.escape(str(t["psnr"]))
        row_values = rf"(?m)^{re.escape(t['method'])}\s+(?:-\s+-\s+-\s+100%|{score}\s+\S+\s+\S+\s+\S+%)\s+{t['latency_s']}\s+"
        row_values += re.escape(str(t["speedup"]) + "×") if t["speedup"] is not None else "-"
        require(re.search(row_values, table) is not None, f"Table 1 mismatch, row {row['id']}")
    source_image = source_doc.extract_image(ref["xref"])["image"]
    bitmap = pdf.Pixmap(source_doc, ref["xref"]).pil_image().convert("RGB")
    pixels = np.asarray(bitmap)
    rect = pdf.Rect(ref["bbox"])
    layout = {"id": recipe["id"], "size_px": recipe["size_px"],
              "size_pt": [rect.width, rect.height], "palette": recipe["palette"],
              "frame_selection": recipe["selection"], "metric_scope": recipe["metric_scope"],
              "labels": [], "frames": []}
    reference = pdf.open()
    page_ref = reference.new_page(width=rect.width, height=rect.height)
    page_ref.insert_image(page_ref.rect, stream=source_image, keep_proportion=False)
    reference.save(out / "reference.pdf", garbage=4, deflate=True)
    reference.close()
    frame_dir = out / "frames"
    frame_dir.mkdir(exist_ok=True)
    for row in recipe["rows"]:
        for j, ((x0, x1), checksum) in enumerate(zip(recipe["columns_px"], row["rgb_sha256"])):
            y0, y1 = row["frame_y"]
            box = [x0, y0, x1, y1]
            frame = bitmap.crop(box)
            require(digest(frame.tobytes()) == checksum, f"frame RGB mismatch: {row['id']}:{j + 1}")
            filename = f"frames/{row['id']}-{j + 1:02}.png"
            frame.save(out / filename)
            layout["frames"].append({"row": row["id"], "ordinal": j + 1, "file": filename,
                                     "frame_rgb_sha256": checksum, "source_px": box, "place_px": box})
    for line in [*recipe["rows"], recipe["prompt"]]:
        layout["labels"].extend(ink_words(pixels, line))
    capture_print_matte(layout, pixels, out)
    return layout, pixels


def capture_print_matte(layout, pixels, out):
    """Separate original word ink from the image codec's nearly white matte."""
    covered = np.zeros(pixels.shape[:2], bool)
    (out / "words").mkdir(exist_ok=True)
    for item in layout["frames"]:
        x, y, w, h = item["source_px"]
        covered[y:h, x:w] = True
    for word in layout["labels"]:
        x, y, w, h = word["ink_box_px"]
        x, y = max(0, x - 4), max(0, y - 4)
        w, h = min(covered.shape[1], w + 4), min(covered.shape[0], h + 4)
        require(not covered[y:h, x:w].any(), "overlapping label patch")
        covered[y:h, x:w] = True
        word["patch_px"] = [x, y, w, h]
        word["patch_file"] = f"words/{word['id']}.png"
        Image.fromarray(pixels[y:h, x:w]).save(out / word["patch_file"])
    mask = (~covered) & (pixels.min(2) != 255)
    indices = np.flatnonzero(mask).astype(np.int32)
    colors = pixels.reshape(-1, 3)[indices]
    require(colors.min() >= 240 and len(indices) < .02 * covered.size,
            "matte is not sparse near-white JPEG ringing; refuse to hide evidence in it")
    layout["matte"] = {"file": "paper-matte.npz", "count": len(indices),
                       "min_channel": int(colors.min()), "description": "Sparse near-white JPEG residues outside independent frames and words; no glyph or frame content."}
    np.savez_compressed(out / layout["matte"]["file"], indices=indices, colors=colors)


def faithful(layout, root, output, component_output=None):
    """Assemble exact native pixels. No access to reference.pdf or the source JPEG."""
    w, h = layout["size_px"]
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    metadata = layout["matte"]
    with np.load(root / metadata["file"], allow_pickle=False) as residual:
        pos, colors = residual["indices"], residual["colors"]
        require(len(pos) == metadata["count"] and np.all((0 <= pos) & (pos < w * h)) and
                colors.min() >= 240 and len(pos) < .02 * w * h and colors.shape == (len(pos), 3),
                "matte violates evidence boundary")
        canvas.reshape(-1, 3)[pos] = colors
    items = ([(f, "place_px", "file") for f in layout["frames"]] +
             [(f, "patch_px", "patch_file") for f in layout["labels"]])
    for item, rect_key, file_key in items:
        x, y, right, bottom = item[rect_key]
        with Image.open(root / item[file_key]) as im:
            require(im.size == (right-x, bottom-y), "exact mode never resizes an evidence layer")
            canvas[y:bottom, x:right] = np.asarray(im.convert("RGB"))
    data = io.BytesIO()
    Image.fromarray(canvas).save(data, format="PNG")
    doc = pdf.open()
    page = doc.new_page(width=layout["size_pt"][0], height=layout["size_pt"][1])
    # Flatten only the reassembled REVIEW OUTPUT, avoiding device-dependent tile seams.
    # Editable component positions, rasters, vector text and native text stay alongside it.
    page.insert_image(page.rect, stream=data.getvalue(), keep_proportion=False)
    doc.save(output, garbage=4, deflate=True)
    doc.close()
    if component_output:
        doc = pdf.open()
        page = doc.new_page(width=layout["size_pt"][0], height=layout["size_pt"][1])
        sx, sy = page.rect.width / w, page.rect.height / h
        # Independent PDF image placements have independent device rounding; keep the
        # seamless export above for printing. Near-white JPEG residue belongs only to it.
        for item, rect_key, file_key in items:
            x, y, right, bottom = item[rect_key]
            page.insert_image(pdf.Rect(x*sx, y*sy, right*sx, bottom*sy),
                              filename=str(root/item[file_key]), keep_proportion=False)
        doc.save(component_output, garbage=4, deflate=True)
        doc.close()
        with pdf.open(component_output) as doc:
            actual = doc[0].get_image_info(xrefs=True)
            require(len(actual) == len(items), "missing faithful PDF component")
            for (item, rect_key, file_key), image in zip(items, actual):
                target = np.array(item[rect_key]) * [sx, sy, sx, sy]
                require(np.max(np.abs(target - image["bbox"])) < .001, "shifted component")
                with Image.open(root/item[file_key]) as im:
                    require(pdf.Pixmap(doc, image["xref"]).samples == im.convert("RGB").tobytes(),
                            "changed component RGB in PDF")
    return canvas


def trace_word(word, pixels, palette):
    """Trace 50% ink coverage with subpixel interpolation; JPEG fringes aren't vectors."""
    x0, y0, x1, y1 = word["ink_box_px"]
    x0, y0 = max(0, x0 - 3), max(0, y0 - 3)
    patch = pixels[y0:y1 + 3, x0:x1 + 3].astype(float)
    absorb = 255.0 - np.array(rgb(palette[word["ink"]]), dtype=float)
    alpha = (255 - patch) @ absorb / (absorb @ absorb)
    points = contourpy.contour_generator(z=np.pad(alpha, 1)).lines(.5)
    return [p + [x0 - .5, y0 - .5] for p in points if len(p) >= 4]


def place_native_word(page, word, layout, font, sx, sy):
    """Fit actual font ink, not the font's typographic line box, into the print box."""
    token = word["text"]
    position, union = 0., pdf.Rect()
    for c in token:
        b = font.glyph_bbox(ord(c))
        union |= pdf.Rect(b.x0 + position, b.y0, b.x1 + position, b.y1)
        position += font.glyph_advance(ord(c))
    require(union.width > 0 and union.height > 0, "cannot typeset " + token)
    x0, y0, x1, y1 = word["ink_box_px"]
    ax, ay = (x1 - x0) * sx / union.width, (y1 - y0) * sy / union.height
    baseline = pdf.Point(x0 * sx - ax * union.x0, y0 * sy + ay * union.y1)
    color = tuple(x / 255 for x in rgb(layout["palette"][word["ink"]]))
    page.insert_text(baseline, token, fontname="FFItalic", fontsize=ay,
                     morph=(baseline, pdf.Matrix(ax / ay, 1)), color=color)


def compose(layout, asset_dir, output, pixels=None, font_path=None):
    w, h = layout["size_pt"]
    sx, sy = w / layout["size_px"][0], h / layout["size_px"][1]
    doc = pdf.open()
    page = doc.new_page(width=w, height=h)
    for item in layout["frames"]:
        x0, y0, x1, y1 = item["place_px"]
        path = asset_dir / item["file"]
        with Image.open(path) as im:
            require(abs(im.width / im.height - (x1 - x0) / (y1 - y0)) < .002,
                    f"Do not stretch frame {path.name}: crop to its target aspect first.")
        page.insert_image(pdf.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                          filename=str(path), keep_proportion=False)
    if pixels is None:
        font = pdf.Font(fontfile=str(font_path)) if font_path else pdf.Font("heit")
        page.insert_font(fontname="FFItalic", fontbuffer=font.buffer)
        for word in layout["labels"]:
            place_native_word(page, word, layout, font, sx, sy)
        doc.subset_fonts()
    else:
        for word in layout["labels"]:
            shape = page.new_shape()
            paths = trace_word(word, pixels, layout["palette"])
            require(paths, f"no contours: {word['id']}")
            for path in paths:
                shape.draw_polyline([pdf.Point(float(x * sx), float(y * sy)) for x, y in path])
            fill = tuple(x / 255 for x in rgb(layout["palette"][word["ink"]]))
            shape.finish(fill=fill, color=None, width=0, even_odd=True)
            shape.commit()
    doc.save(output, garbage=4, deflate=True)
    doc.close()


def check(output, reference, layout, *, outlines):
    with pdf.open(output) as candidate, pdf.open(reference) as original:
        page = candidate[0]
        require(len(candidate) == 1, "wrong page count")
        items = page.get_image_info(xrefs=True)
        require(len(items) == 15, "must contain fifteen independent image placements")
        sx, sy = (p / i for p, i in zip(layout["size_pt"], layout["size_px"]))
        for item, frozen in zip(items, layout["frames"]):
            pix = pdf.Pixmap(candidate, item["xref"])
            require(digest(pix.samples) == frozen["frame_rgb_sha256"], "PDF frame order/content changed")
            dest = np.asarray(frozen["place_px"]) * [sx, sy, sx, sy]
            require(np.max(np.abs(dest - item["bbox"])) < .001, "PDF frame placement changed")
        if outlines:
            require(len(page.get_drawings()) == len(layout["labels"]), "missing word outline")
        else:
            tokens = page.get_text("words")
            require("".join(t[4] for t in tokens).replace(" ", "") ==
                    "".join(w["text"] for w in layout["labels"]), "native PDF text differs from transcription")
        pm = [p.get_pixmap(dpi=240, alpha=False) for p in (page, original[0])]
        diff = abs(np.frombuffer(pm[0].samples, np.uint8).astype(float) -
                   np.frombuffer(pm[1].samples, np.uint8))
        return {"frame_images": len(items), "paper_width_pt": round(page.rect.width, 6),
                "distinct_frame_rgb_checksums": len({i["frame_rgb_sha256"] for i in layout["frames"]}),
                "word_outlines" if outlines else "native_words": len(layout["labels"]),
                "mae_240dpi_rgb_levels": round(float(diff.mean()), 6),
                "tested_rgb_scale": "0..255", "rgb_channels_within_3_240dpi": round(float((diff <= 3).mean()), 6)}


def faithful_metrics(output, reference):
    result = {}
    with pdf.open(output) as rec, pdf.open(reference) as ref:
        for dpi in (144, 240, 300):
            a, b = (np.frombuffer(d[0].get_pixmap(dpi=dpi, alpha=False).samples, np.uint8)
                    for d in (rec, ref))
            delta = abs(a.astype(np.int16) - b)
            result[str(dpi)] = {"mae_rgb_levels": round(float(delta.mean()), 6),
                                "max_channel_delta": int(delta.max()),
                                "different_pixels": int((delta.reshape(-1, 3) != 0).any(1).sum())}
    return result


def poppler_metrics(output, reference):
    tool = shutil.which("pdftoppm")
    if not tool:
        return {"status": "not run: pdftoppm unavailable"}
    result = {}
    def raster(path, dpi):
        data = subprocess.run([tool, "-r", str(dpi), "-singlefile", "-png", str(path)],
                              capture_output=True, check=True).stdout
        with Image.open(io.BytesIO(data)) as im:
            return np.asarray(im.convert("RGB"), dtype=np.int16)
    for dpi in (144, 240, 300):
        diff = np.abs(raster(output, dpi) - raster(reference, dpi))
        result[str(dpi)] = {"mae_rgb_levels": round(float(diff.mean()), 9),
                            "max_channel_delta": int(diff.max()),
                            "different_pixels": int((diff != 0).any(2).sum())}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--source", type=Path, help="pinned CVF conference PDF")
    options.add_argument("--template", type=Path, help="layout.json from prior build; paths relative to it")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--font", type=Path, help="optional local italic TTF/OTF for the native branch")
    parser.add_argument("--style", choices=["native", "faithful"], default="native", help="template mode: re-typeset the current text or replay the printed word patches")
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if args.template:
        layout = json.loads(args.template.read_text())
        if args.style == "faithful":
            faithful(layout, args.template.parent, out / "custom.pdf")
        else:
            compose(layout, args.template.parent, out / "custom.pdf", font_path=args.font)
        return
    recipe = json.loads(RECIPE.read_text())
    with pdf.open(args.source) as source:
        layout, pixels = build_layout(source, recipe, out)
    save_json(out / "layout.json", layout)
    replay = faithful(layout, out, out / "seamless.pdf", out / "reconstruction.pdf")
    require(np.array_equal(replay, pixels), "independent component replay differs from decoded source")
    compose(layout, out, out / "vectors.pdf", pixels)
    compose(layout, out, out / "native.pdf", font_path=args.font)
    receipt = {"id": recipe["id"], "source_url": recipe["source"], "source_sha256": recipe["sha256"],
               "recipe_sha256": digest(RECIPE.read_bytes()), "preserve": recipe["preserve"],
               "evidence_status": "measured", "evidence_owner": "paper authors; no new model run",
               "metric_scope": recipe["metric_scope"], "frame_selection": recipe["selection"],
               "layout": "layout.json", "review": "15 original frame crops checked against independent per-slot RGB hashes, coordinate tolerance 0.001 pt. Reassembled native RGB proof; vector-word and selectable re-typeset alternatives separate.",
               "source_bbox_pt": recipe["page_bbox_pt"], "native_font": pdf.Font(fontfile=str(args.font)).name if args.font else pdf.Font("heit").name,
               "scope_limits": "Label colors and contours are recovered from a JPEG; compression fringes, font identity and true timestamps are not recoverable."}
    for filename in ["vectors.pdf", "native.pdf"]:
        receipt[filename] = check(out / filename, out / "reference.pdf", layout, outlines=filename == "vectors.pdf")
    receipt["reconstruction.pdf"] = {
        "frames": len(layout["frames"]), "original_word_images": len(layout["labels"]),
        "components_checked_bbox_tolerance_pt": .001,
        "rendered_comparison": faithful_metrics(out/"reconstruction.pdf", out/"reference.pdf"),
        "note": "Independent placements of all frame and ink RGB patches. Separate-image resampling can differ from one-image downsampling; excludes the sparse near-white JPEG matte."
    }
    receipt["seamless.pdf"] = {
        "native_size_px": recipe["size_px"], "native_rgb_sha256": digest(replay.tobytes()),
        "different_source_pixels": int((pixels != replay).any(2).sum()),
        "frame_components": len(layout["frames"]), "word_components": len(layout["labels"]),
        "sparse_matte": layout["matte"], "rendered_comparison": faithful_metrics(out/"seamless.pdf", out/"reference.pdf"),
        "note": "Reassembled proof flattened only at export. At lower DPI MuPDF may decode the author's JPEG at reduced resolution while the lossless reassembly follows standard RGB downsampling."
    }
    receipt["seamless.pdf"]["poppler_comparison"] = poppler_metrics(out/"seamless.pdf", out/"reference.pdf")
    receipt["outputs"] = {f: digest((out / f).read_bytes()) for f in ["reference.pdf", "reconstruction.pdf", "seamless.pdf", "vectors.pdf", "native.pdf", "layout.json"]}
    save_json(out / "receipt.json", receipt)


if __name__ == "__main__":
    main()
