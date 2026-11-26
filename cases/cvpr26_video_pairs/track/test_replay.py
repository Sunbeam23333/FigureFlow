"""Source-free test: changing a named slot must change only that slot, not the neighboring evidence."""

import tempfile
import unittest
from pathlib import Path


class TrackEditTests(unittest.TestCase):
    def test_slot_replacement_and_aspect_guard(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF reproduction extra not installed")
        from PIL import Image
        from pypdf import PdfReader

        from cases.cvpr26_video_pairs.track.build import assemble

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for filename, size, color in [
                ("left", (10, 10), "red"),
                ("right", (10, 10), "blue"),
                ("new", (10, 10), "green"),
                ("bad", (10, 16), "green"),
            ]:
                Image.new("RGB", size, color).save(root / (filename + ".png"))
            with fitz.open() as mats:
                page = mats.new_page(width=20, height=10)
                for j, name in enumerate(["left", "right"]):
                    page.insert_image(
                        fitz.Rect(j * 10, 0, j * 10 + 10, 10), filename=str(root / (name + ".png"))
                    )
                mats.save(root / "materials.pdf")
            resources = list(PdfReader(root / "materials.pdf").pages[0]["/Resources"]["/XObject"])
            scene = {
                "paper_size_pt": [20, 10],
                "page_crop_pt": [0, 0, 20, 10],
                "placement": [1, 0, 0, 1, 0, 0],
                "clip": "0 0 20 10 re W n",
                "layers": [
                    {
                        "id": side,
                        "kind": "image",
                        "resource": res,
                        "group": side,
                        "instructions": [f"10 0 0 10 {i * 10} 0 cm", f"{res} Do"],
                    }
                    for i, (side, res) in enumerate(zip(["left", "right"], resources))
                ],
            }
            out = root / "custom.pdf"
            assemble(scene, root / "materials.pdf", out, {"images": {"left": "new.png"}}, root)
            with fitz.open(out) as pdf:
                pix = pdf[0].get_pixmap()
                self.assertEqual(pix.pixel(5, 5), (0, 128, 0))
                self.assertEqual(pix.pixel(15, 5), (0, 0, 255))
            with self.assertRaisesRegex(ValueError, "aspect ratio"):
                assemble(scene, root / "materials.pdf", out, {"images": {"left": "bad.png"}}, root)
            with self.assertRaisesRegex(ValueError, "unknown layer"):
                assemble(scene, root / "materials.pdf", out, {"layers": {"typo": [1, 0, 0, 1, 0, 0]}}, root)
