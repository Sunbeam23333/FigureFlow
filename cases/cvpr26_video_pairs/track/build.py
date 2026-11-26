"""Rebuild the teaser from individual image, path and text paints; never replay a full figure on the right."""

import argparse
import hashlib
import io
import json
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject, NameObject

HERE = Path(__file__).resolve().parent
TEMPLATE = json.loads((HERE / "template.json").read_text())
I = [1, 0, 0, 1, 0, 0]
PATH = {b"m", b"l", b"c", b"h", b"re", b"W", b"W*"}
STATE = {b"cm", b"cs", b"sc", b"CS", b"SC", b"ri", b"j", b"w", b"M"}
PAINT = {b"f", b"f*", b"S"}
# Named, audited groups of paint events in the pinned form, inclusive end indexes.
GROUPS = [
    (13, "paper"),
    (76, "joint.input"),
    (134, "joint.output"),
    (288, "joint.estimated"),
    (305, "joint.input"),
    (442, "joint.edited"),
    (459, "joint.output"),
    (471, "joint.arrow-output"),
    (529, "deform.input"),
    (587, "deform.output"),
    (605, "deform.input"),
    (622, "deform.output"),
    (680, "transfer.input"),
    (738, "transfer.output"),
    (756, "transfer.input"),
    (773, "transfer.output"),
    (831, "removal.input"),
    (889, "removal.output"),
    (907, "removal.input"),
    (924, "removal.output"),
    (936, "joint.arrow-edit"),
    (945, "joint.arrow-estimate"),
    (995, "deform.heading"),
    (1007, "deform.arrow"),
    (1016, "transfer.arrow"),
    (1025, "removal.arrow"),
    (1054, "transfer.heading"),
    (1085, "removal.heading"),
    (1116, "joint.heading"),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def require(condition, msg):
    if not condition:
        raise ValueError(msg)


def syntax(args, op):
    buffer = io.BytesIO()
    for a in args:
        a.write_to_stream(buffer)
        buffer.write(b" ")
    buffer.write(op)
    return buffer.getvalue().decode("latin-1")


def image_ids():
    slots = {
        n: f"{group}.{depth}"
        for group, ns in TEMPLATE["frame_stacks"].items()
        for depth, n in zip(TEMPLATE["published_layers_back_to_front"], ns)
    }
    return slots | {n: group for group, n in TEMPLATE["track_projections"].items()}


def split_paints(ops):
    """Isolate each paint with a snapshot of its inherited graphics state and clips.

    Intentionally supports only the operators used by this source. A novel operator
    must not silently disappear or make an apparently successful exact replay.
    """
    scopes, path, text, layers = [[]], [], [], []
    slots = image_ids()
    for index, (args, op) in enumerate(ops):
        cmd = syntax(args, op)
        if op == b"q":
            scopes.append([])
        elif op == b"Q":
            require(not path and not text and len(scopes) > 1, "corrupt graphics state")
            scopes.pop()
        elif op in STATE:
            require(not path and not text, "unexpected mid-path state change")
            scopes[-1].append(cmd)
        elif op in PATH:
            path.append(cmd)
        elif op == b"n":
            if path:
                require(path[-1] in ("W", "W*"), "unknown nonpainted path")
                scopes[-1].extend([*path, "n"])
                path = []
        elif op == b"BT":
            require(not text, "nested text object")
            text = ["BT"]
        elif op in {b"Tc", b"Tm", b"Tf"}:
            require(bool(text), "text state outside BT")
            text.append(cmd)
        elif op == b"ET":
            text = []
        elif op in PAINT | {b"Do", b"TJ", b"Tj"}:
            name = next(name for end, name in GROUPS if index <= end)
            kind = "image" if op == b"Do" else "text" if text else "path"
            layer = {"id": f"{name}.{index}", "group": name, "kind": kind}
            if kind == "image":
                asset = int(str(args[0]).removeprefix("/Im"))
                layer.update(id=slots[asset], resource=f"/Im{asset}")
            layer["instructions"] = [item for scope in scopes for item in scope] + [
                *text,
                *path,
                cmd,
                *(["ET"] if text else []),
            ]
            layers.append(layer)
            path = []
        else:
            raise ValueError(f"unsupported PDF operator: {op}")
    require(len(scopes) == 1 and not path and not text, "unbalanced source")
    require(len(layers) == 123, "expected 26 images + 51 paths + 46 text paints")
    require(
        [x["id"] for x in layers if x["kind"] == "image"] == [slots[i] for i in range(1, 27)],
        "frame or trajectory order changed",
    )
    return layers


def make_page(path, size, resources, program):
    writer = PdfWriter()
    page = writer.add_blank_page(*size)
    page[NameObject("/Resources")] = resources.clone(writer)
    stream = DecodedStreamObject()
    stream.set_data(program.encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    writer.write(path)


def crop_paper(destination, paper, crop):
    """Keep the original paper CTM until after painting, including its rounding at print resolution."""
    box = fitz.Rect(crop)
    with fitz.open() as result:
        result.new_page(width=box.width, height=box.height)
        result[0].show_pdf_page(result[0].rect, paper, 0, clip=box)
        result.save(destination, garbage=4, deflate=True, no_new_id=True)


def scene_page(path, scene, resources, program):
    buf = io.BytesIO()
    make_page(buf, scene["paper_size_pt"], resources, program)
    with fitz.open(stream=buf.getvalue(), filetype="pdf") as synthetic_paper:
        crop_paper(path, synthetic_paper, scene["page_crop_pt"])


def matrix(m):
    require(
        isinstance(m, list) and len(m) == 6 and all(type(v) in (float, int) and abs(v) < 1e8 for v in m),
        "invalid affine matrix",
    )
    return " ".join(str(x) for x in m) + " cm"


def assemble(scene, materials, out, overrides=None, base=None):
    """Public replay interface: scene and material store are independent of the paper."""
    overrides = overrides or {}
    require(set(overrides) <= {"images", "groups", "layers"}, "unknown override key")
    store = PdfReader(materials)
    res = store.pages[0]["/Resources"]
    slots = {l["id"]: l["resource"] for l in scene["layers"] if l["kind"] == "image"}
    require(set(overrides.get("images", {})) <= slots.keys(), "unknown image slot")
    require(set(overrides.get("groups", {})) <= {l["group"] for l in scene["layers"]}, "unknown group")
    require(set(overrides.get("layers", {})) <= {l["id"] for l in scene["layers"]}, "unknown layer")
    for slot, filename in overrides.get("images", {}).items():
        # MuPDF creates image resources with the original pixel dimensions and real alpha.
        with fitz.open() as tmp:
            page = tmp.new_page()
            page.insert_image(page.rect, filename=str(base / filename))
            replacement = PdfReader(io.BytesIO(tmp.tobytes()))
        xobj = replacement.pages[0]["/Resources"]["/XObject"]
        new = next(iter(xobj.values()))
        old = res["/XObject"][slots[slot]]
        ratio = old["/Width"] / old["/Height"]
        target = new.get_object()
        require(
            abs((target["/Width"] / target["/Height"]) / ratio - 1) < 0.01,
            f"{slot}: replacement aspect ratio differs by >=1%; crop or pad explicitly",
        )
        res["/XObject"][NameObject(slots[slot])] = new
    parts = ["q", matrix(scene["placement"]), scene["clip"]]
    for l in scene["layers"]:
        parts.append("q")
        change = overrides.get("groups", {}).get(l["group"])
        if change is not None:
            parts.append(matrix(change))
        if l["id"] in overrides.get("layers", {}):
            parts.append(matrix(overrides["layers"][l["id"]]))
        parts.extend([*l["instructions"], "Q"])
    scene_page(out, scene, res, "\n".join([*parts, "Q"]))


def shape_proof(source, candidate, crop):
    def inventory(page):
        by_xref = {im[0]: im[1] for im in page.get_images()}

        def mask_hash(x):
            return hashlib.sha256(page.parent.xref_stream(x)).hexdigest() if x else None

        return [
            (r["digest"].hex(), mask_hash(by_xref[r["xref"]]), list(r["transform"]))
            for r in page.get_image_info(xrefs=True)
        ]

    with fitz.open(source) as src, fitz.open(candidate) as dst:
        a, b = inventory(src[0]), inventory(dst[0])
        require(len(a) == len(b) == 26, "image is missing or duplicated")
        require([s[:2] for s in a] == [s[:2] for s in b], "RGB pixels, masks, or z order changed")
        delta = max(
            abs(s[2][j] - (crop[j - 4] if j >= 4 else 0) - t[2][j]) for s, t in zip(a, b) for j in range(6)
        )
        require(delta < 0.001, f"frame-placement error: {delta} pt")

        def spans(page, box):
            return [
                (s["text"].strip(), s["font"], s["color"])
                for bl in page.get_text("dict", clip=box, flags=fitz.TEXTFLAGS_TEXT)["blocks"]
                for ln in bl.get("lines", [])
                for s in ln["spans"]
            ]

        native = spans(src[0], fitz.Rect(crop))
        require(spans(dst[0], dst[0].rect) == native, "editable caption, font, or ink changed")
        return {
            "images_in_source_order": len(a),
            "soft_masks_compared": sum(bool(s[1]) for s in a),
            "native_label_spans": len(native),
            "max_affine_delta_pt": delta,
            "placements": [
                {
                    "slot": image_ids()[i],
                    "source_display_digest_md5": s[0],
                    "soft_mask_sha256": s[1],
                    "source_transform": s[2],
                    "candidate_transform": t[2],
                }
                for i, (s, t) in enumerate(zip(a, b), 1)
            ],
        }


def build(source, out):
    require(digest(source) == TEMPLATE["source_sha256"], "not the pinned CVF PDF; see template.json")
    out.mkdir(parents=True, exist_ok=True)
    rd = PdfReader(source)
    page = rd.pages[0]
    outer = page["/Resources"]["/XObject"]["/Fm1"]
    figure = outer["/Resources"]["/XObject"]["/Im1"]
    res = figure["/Resources"]
    require(
        all(v.get_object()["/Subtype"] == "/Image" for v in res["/XObject"].values()),
        "material library must not include a whole source form",
    )
    crop = TEMPLATE["page_crop_top_left_pt"]
    size = [crop[2] - crop[0], crop[3] - crop[1]]
    ox, oy = TEMPLATE["figure_origin_bottom_left_page_pt"]
    s = TEMPLATE["figure_scale"]
    placement = [s, 0, 0, s, ox, oy]
    bbox = outer["/BBox"]
    require(list(bbox[:2]) == [0, 0], "changed outer clipping origin")
    clip = f"0 0 {bbox[2]} {bbox[3]} re W n"
    # Only the LEFT reference uses the unmodified author form. RIGHT starts from blank paper.
    scene = {
        "template": TEMPLATE["id"],
        "size_pt": size,
        "page_crop_pt": crop,
        "paper_size_pt": [float(page.mediabox.width), float(page.mediabox.height)],
        "placement": placement,
        "clip": clip,
        "layers": split_paints(ContentStream(figure, rd).operations),
    }
    scene_page(
        out / "reference.pdf",
        scene,
        DictionaryObject(
            {NameObject("/XObject"): DictionaryObject({NameObject("/Reference"): outer.indirect_reference})}
        ),
        f"q\n{matrix(placement)}\n/Reference Do\nQ",
    )
    make_page(out / "materials.pdf", size, res, "")
    dump(out / "scene.json", scene)
    assemble(scene, out / "materials.pdf", out / "reconstruction.pdf")
    proof = shape_proof(source, out / "reconstruction.pdf", crop)
    with (
        fitz.open(out / "reference.pdf") as ref,
        fitz.open(out / "reconstruction.pdf") as rec,
        fitz.open(source) as paper,
        fitz.open() as direct,
    ):
        import numpy as np

        direct.new_page(width=size[0], height=size[1])
        direct[0].show_pdf_page(direct[0].rect, paper, 0, clip=fitz.Rect(crop))
        pix = [doc[0].get_pixmap(dpi=240, alpha=False) for doc in [ref, rec]]
        # Compare saved-and-reopened PDFs on both sides: MuPDF's in-memory graft
        # and its serialized representation can render a few channel levels apart.
        with fitz.open(stream=direct.tobytes(), filetype="pdf") as printed:
            require(
                pix[0].samples == printed[0].get_pixmap(dpi=240, alpha=False).samples,
                "reference differs from an independent crop on the official proceedings page",
            )
        diff = np.abs(
            np.frombuffer(pix[0].samples, dtype=np.uint8).astype("int16")
            - np.frombuffer(pix[1].samples, dtype=np.uint8)
        ).reshape(-1, 3)
        m = {
            "dpi": 240,
            "pixel_size": [pix[0].width, pix[0].height],
            "mean_absolute_channel_error_0_255": float(diff.mean()),
            "fraction_pixels_changed": float(np.any(diff, axis=1).mean()),
            "max_absolute_channel_error": int(diff.max()),
            "reference_equals_direct_paper_crop": True,
        }
        require(m["max_absolute_channel_error"] == 0, f"visual drift: {m}")
    dump(
        out / "receipt.json",
        {
            "template": TEMPLATE["id"],
            "source_sha256": digest(source),
            "template_sha256": digest(HERE / "template.json"),
            "builder_sha256": digest(Path(__file__)),
            "source_url": TEMPLATE["source_url"],
            "evidence_status": TEMPLATE["evidence_status"],
            "source_crop_pt": crop,
            "measured_visual_difference": m,
            "semantic_proof": proof,
            "preserve": TEMPLATE["preserve"],
            "files_sha256": {
                name: digest(out / name)
                for name in ["scene.json", "materials.pdf", "reference.pdf", "reconstruction.pdf"]
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path, help="official CVF paper; builds a verified source replay")
    mode.add_argument("--scene", type=Path, help="recompose an extracted local scene, without the paper")
    parser.add_argument(
        "--overrides", type=Path, help="optional image replacements/group transforms for --scene"
    )
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args()
    if args.source:
        require(not args.overrides, "customization is not a source reproduction; use --scene")
        build(args.source, args.out)
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        edits = json.loads(args.overrides.read_text()) if args.overrides else {}
        base = args.overrides.parent if args.overrides else args.scene.parent
        assemble(
            json.loads(args.scene.read_text()),
            args.scene.parent / "materials.pdf",
            args.out / "custom.pdf",
            edits,
            base,
        )
        dump(
            args.out / "custom_receipt.json",
            {
                "mode": "custom; not an exact-source validation",
                "scene_sha256": digest(args.scene),
                "materials_sha256": digest(args.scene.parent / "materials.pdf"),
                "overrides": edits,
                "replacement_sha256": {k: digest(base / v) for k, v in edits.get("images", {}).items()},
                "output_sha256": digest(args.out / "custom.pdf"),
            },
        )
