"""Build and review the two CVPR video figures. Network use is opt-in (fetch only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
from cases.paper_rebuilds.fetch_sources import check_existing, fetch_one

SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
ATLAS = "figureflow-video-fig1-comparison.pdf"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probes(slug):
    """Named regions, not a global similarity score. Coordinate convention: top-left."""
    if slug == "track":
        return SOURCES[slug]["regions"]
    regions = {}
    # Probe the interiors, not a gutter shared by two independent image resamplers.
    for row, y in zip(("dense", "rapid", "turbo"), (69, 388, 707)):
        for k, x in enumerate((.015, .21, .41, .61, .81), 1):
            regions[f"{row}.frame{k}"] = (x, (y + 8) / 1016, x + .165, (y + 239) / 1016)
        regions[f"{row}.metric_ink"] = (0, (y - 66) / 1016, .59, (y - 1) / 1016)
    regions["shared_prompt"] = (.05, 957 / 1016, .95, 1.0)
    return regions


def pixels(page, dpi):
    import numpy as np
    import pymupdf as pdf

    pix = page.get_pixmap(dpi=dpi, colorspace=pdf.csRGB, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)


def compare_pixels(ref, candidate, regions):
    """Reject displaced/empty evidence regions even when most of a page is white."""
    import numpy as np

    if ref.shape != candidate.shape:
        raise ValueError("different raster sizes")
    delta = np.abs(ref.astype(np.int16) - candidate.astype(np.int16))
    peak = delta.max(axis=2)
    h, w = peak.shape
    result = {
        "size_px": [w, h], "equal_rgb_pct": float(100 * (peak == 0).mean()),
        "max_channel_error": int(peak.max()), "regions": {},
    }
    for key, (x0, y0, x1, y1) in regions.items():
        region = (slice(round(h*y0), round(h*y1)), slice(round(w*x0), round(w*x1)))
        ink = np.minimum(ref[region].min(axis=2), candidate[region].min(axis=2)) < 235
        if not ink.any():
            raise ValueError(f"empty evidence probe: {key}")
        ink_error = float(delta[region][ink].mean())
        severe = float((peak[region][ink] > 64).mean())
        # 8-bit RGB; intentionally check localized artifacts, not aesthetic quality.
        if ink_error > 12 or severe > .12:
            raise ValueError(f"visually displaced evidence: {key}: MAE {ink_error:.3f}, severe {severe:.2%}")
        result["regions"][key] = {
            "foreground_mean_channel_error": round(ink_error, 5),
            "foreground_fraction_max_error_gt64": round(severe, 7),
        }
    return result


def audit_case(folder, slug, source):
    import pymupdf as pdf

    with pdf.open(folder / "reference.pdf") as ref, pdf.open(folder / "reconstruction.pdf") as rec, \
            pdf.open(folder / SOURCES[slug]["display"]) as display:
        for doc in (rec, display):
            if len(ref) != 1 or len(doc) != 1 or any(abs(a-b) > .01 for a, b in zip(ref[0].rect, doc[0].rect)):
                raise ValueError(f"{slug}: pages or print dimensions do not match")
        visible_images = [i for i in rec[0].get_image_info() if rec[0].rect.intersects(i["bbox"])]
        if len(visible_images) < SOURCES[slug]["minimum_image_placements"]:
            raise ValueError(f"{slug}: expected independent figure components, not a flattened reproduction")
        audits = {str(dpi): compare_pixels(pixels(ref[0], dpi), pixels(display[0], dpi), probes(slug))
                  for dpi in (144, 300)}
        if audits["300"]["max_channel_error"] != 0:
            raise ValueError(f"{slug}: 300 dpi print display differs from the pinned reference")
        # Independently render the official *page* cropped to the figure. This also catches
        # a reference and candidate that are identically wrong due to a shared transform.
        recipe, crop_field = (("track/template.json", "page_crop_top_left_pt") if slug == "track"
                              else ("rapid/recipe.json", "page_bbox_pt"))
        box = json.loads((ROOT / recipe).read_text(encoding="utf-8"))[crop_field]
        with pdf.open(source) as original:
            page = original[0]
            page.set_cropbox(pdf.Rect(box))
            if (pixels(page, 300) != pixels(ref[0], 300)).any():
                raise ValueError(f"{slug}: reference is not the official page crop")
        return {
            "paper_width_bp": round(rec[0].rect.width, 4), "paper_height_bp": round(rec[0].rect.height, 4),
            "image_placements": len(visible_images), "raster_checks": audits,
            "reference_vs_official_page_300dpi": "identical",
            "reference_sha256": digest(folder / "reference.pdf"),
            "candidate_sha256": digest(folder / "reconstruction.pdf"),
            "display_file": SOURCES[slug]["display"], "display_sha256": digest(folder / SOURCES[slug]["display"]),
            "component_receipt_sha256": digest(folder / "receipt.json"),
        }


def audit_mount(page, folder, display="reconstruction.pdf"):
    """Check the *final* TeX page: every visible image still has its original print geometry."""
    import pymupdf as pdf

    mounted = [pdf.Rect(i["bbox"]) for i in page.get_image_info()]
    errors = {}
    for filename, left in (("reference.pdf", True), (display, False)):
        with pdf.open(folder / filename) as doc:
            panel = doc[0]
            dx = 20 if left else panel.rect.width + 40
            expected = [pdf.Rect(i["bbox"]) + (dx, 80, dx, 80) for i in panel.get_image_info()
                        if panel.rect.intersects(i["bbox"])]
            actual = [r for r in mounted if dx <= (r.x0 + r.x1) / 2 <= dx + panel.rect.width
                      and 80 <= (r.y0 + r.y1) / 2 <= 80 + panel.rect.height]
            if not expected or len(expected) != len(actual):
                raise ValueError(f"missing or extra mounted components: {filename}")
            worst = max(abs(a-b) for first, second in zip(expected, actual) for a, b in zip(first, second))
            if worst > .08:
                raise ValueError(f"mounted print geometry changed by {worst:.4f} bp: {filename}")
            errors[filename] = round(worst, 6)
    return errors


def build(source_dir, dest):
    import pymupdf as pdf

    dest = dest.resolve()
    if dest.exists():
        raise ValueError(f"output already exists; choose a new directory to preserve previous work: {dest}")
    for slug, paper in SOURCES.items():
        check_existing(source_dir / (slug + ".pdf"), paper["sha256"])
    tex = shutil.which("xelatex")
    if not tex:
        raise ValueError("XeLaTeX is needed to typeset the two-page comparison (TeX Live or MacTeX).")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Publish the pair only after both builds, the full atlas, and all probes pass.
    with tempfile.TemporaryDirectory(prefix=".figureflow-proof-", dir=dest.parent) as temp:
        stage = Path(temp) / "proof"
        stage.mkdir()
        report = {"rasterizer": "PyMuPDF " + pdf.VersionBind, "cases": {}}
        for slug, paper in SOURCES.items():
            subprocess.run([sys.executable, str(ROOT / slug / "build.py"), "--source",
                            str((source_dir / (slug + ".pdf")).resolve()), "--out", str(stage / slug)], check=True)
            report["cases"][slug] = dict(source_sha256=paper["sha256"],
                                         **audit_case(stage / slug, slug, source_dir / (slug + ".pdf")))
        shutil.copyfile(ROOT / "comparison.tex", stage / "comparison.tex")
        cmd = [tex, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "comparison.tex"]
        compiled = subprocess.run(cmd, cwd=stage, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  check=False)
        if compiled.returncode or "Overfull " in compiled.stdout or "Missing character:" in compiled.stdout:
            raise ValueError("comparison typesetting failed:\n" + compiled.stdout[-3500:])
        (stage / "comparison.pdf").rename(stage / ATLAS)
        with pdf.open(stage / ATLAS) as atlas:
            if len(atlas) != len(SOURCES):
                raise ValueError("comparison pages missing")
            for page, (slug, paper) in zip(atlas, SOURCES.items()):
                if paper["title"] not in page.get_text():
                    raise ValueError(f"wrong comparison page: {slug}")
                report["cases"][slug]["mount_max_bbox_error_bp"] = audit_mount(page, stage / slug, paper["display"])
                page.get_pixmap(dpi=240, alpha=False).save(stage / f"{slug}-print-240dpi.png")
        report["atlas_sha256"] = digest(stage / ATLAS)
        (stage / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        stage.rename(dest)
    return dest / ATLAS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for op in ("fetch", "build"):
        sub = commands.add_parser(op)
        sub.add_argument("--source-dir", type=Path, default=ROOT / "local/sources")
        if op == "build":
            sub.add_argument("--output-dir", type=Path, default=ROOT / "local/proof")
    args = parser.parse_args()
    try:
        if args.action == "fetch":
            for slug, paper in SOURCES.items():
                print(slug, fetch_one(slug, (paper["url"], paper["sha256"]), args.source_dir), flush=True)
        else:
            print(build(args.source_dir, args.output_dir))
    except (OSError, ValueError, subprocess.CalledProcessError) as err:
        parser.exit(1, f"error: {err}\n")


if __name__ == "__main__":
    main()
