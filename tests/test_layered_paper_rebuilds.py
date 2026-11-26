import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases/paper_rebuilds"
SCRIPT = CASES / "render.py"
IDS = (
    "videoworld_fig1",
    "janus_fig1",
    "janus_fig2",
    "epona_fig1",
    "epona_fig2",
    "graphmimic_fig1",
    "graphmimic_fig2",
    "motus_fig1",
    "dynaview_fig1",
)
try:
    import pymupdf as fitz

    from cases.paper_rebuilds import render
except ImportError:
    render = None


class LayeredRecipeTests(unittest.TestCase):
    def test_recipes_and_edition_consistency(self):
        specs = {f.stem: json.loads(f.read_text()) for f in (CASES / "specs").glob("*.json")}
        self.assertEqual(set(specs), set(IDS))
        for key in IDS:
            s = specs[key]
            self.assertEqual(key, s["id"])
            if render:
                render.validate(s)
            self.assertRegex(s["sha256"], r"^[a-f0-9]{64}$")
            self.assertTrue(s["url"].startswith("https://"))
            for c in s["palette"].values():
                self.assertRegex(c, r"^#[a-fA-F0-9]{6}$")
        self.assertEqual(len({s["sha256"] for s in specs.values()}), 6)
        self.assertEqual(len([x for x in specs["janus_fig1"]["layers"] if x["kind"] == "asset"]), 15)
        self.assertFalse(any(x["kind"] == "asset" for x in specs["janus_fig2"]["layers"]))

    @unittest.skipUnless(render, "optional PyMuPDF / Cairo rebuild runtime missing")
    def test_render_changes_one_layer_without_changing_the_evidence(self):
        from io import BytesIO

        from PIL import Image

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "sample.pdf"
            stream = BytesIO()
            Image.new("RGB", (12, 9), "#4d782c").save(stream, "PNG")
            with fitz.open() as doc:
                page = doc.new_page(width=110, height=70)
                bbox = [10, 20, 34, 38]
                xref = page.insert_image(fitz.Rect(*bbox), stream=stream.getvalue())
                page.insert_text((48, 36), "Source")
                doc.save(src)
            s = {
                "id": "fixture_fig1",
                "paper": "Fixture",
                "figure": "Figure 1",
                "venue": "Local",
                "page": 1,
                "box": [3, 7, 103, 47],
                "url": "https://example.invalid/fixture.pdf",
                "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                "palette": {"ink": "#222222"},
                "limitations": "Local synthetic test.",
                "claim": "Test edit.",
                "family": "image and text",
                "layers": [
                    {"kind": "asset", "id": "sample", "box": bbox, "role": "test image", "xref": xref},
                    {"kind": "text", "id": "label", "text": "Source", "x": 48, "y": 36, "size": 8},
                ],
            }
            out = root / s["id"]
            render.render(s, src, out)
            before = json.loads((out / "provenance.json").read_text())
            s["layers"][1]["text"] = "Changed"
            render.render(s, src, out)
            after = json.loads((out / "provenance.json").read_text())
            self.assertEqual(before["assets"], after["assets"])
            self.assertEqual(before["outputs"]["reference.png"], after["outputs"]["reference.png"])
            self.assertNotEqual(before["outputs"]["candidate.png"], after["outputs"]["candidate.png"])
            with fitz.open(out / "candidate.pdf") as check:
                self.assertEqual(len(check), 1)
                self.assertAlmostEqual(check[0].rect.width, 100, places=2)
                self.assertIn("Changed", check[0].get_text())
            s["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash"):
                render.render(s, src, root / "reject")
            self.assertFalse((root / "reject").exists())

    @unittest.skipUnless(
        render and os.environ.get("FIGUREFLOW_PAPER_PDFS"),
        "set FIGUREFLOW_PAPER_PDFS to test nine real papers' figures",
    )
    def test_nine_local_published_figures(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--all",
                    "--source-dir",
                    os.environ["FIGUREFLOW_PAPER_PDFS"],
                    "--output-dir",
                    str(out),
                ],
                check=True,
            )
            with fitz.open(out / "figureflow_comparisons.pdf") as atlas:
                self.assertEqual(len(atlas), 9)
                for page, key in zip(atlas, IDS):
                    s = json.loads((CASES / "specs" / f"{key}.json").read_text())
                    self.assertIn(s["paper"], page.get_text())
                    self.assertIn("ORIGINAL", page.get_text())
                    self.assertIn("RECONSTRUCTION", page.get_text())
                    provenance = json.loads((out / key / "provenance.json").read_text())
                    self.assertEqual(provenance["source_pdf_sha256"], s["sha256"])
                    svg = ET.parse(out / key / "candidate.svg")
                    imgs = svg.findall(".//{http://www.w3.org/2000/svg}image")
                    self.assertEqual(len(imgs), len(provenance["assets"]))
                    for asset in provenance["assets"]:
                        self.assertEqual(
                            hashlib.sha256((out / key / asset["file"]).read_bytes()).hexdigest(),
                            asset["sha256"],
                        )
            self.assertTrue((out / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
