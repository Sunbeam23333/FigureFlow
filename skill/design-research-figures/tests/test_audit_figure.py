from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from audit_figure import audit, content_bbox, estimated_background  # noqa: E402


class GradientBackgroundAuditTests(unittest.TestCase):
    def _gpu_green_gradient(self) -> Image.Image:
        seed = Image.new("RGB", (180, 100), "#000000")
        seed.putpixel((0, 0), (251, 253, 248))
        seed.putpixel((seed.width - 1, 0), (245, 249, 239))
        seed.putpixel((0, seed.height - 1), (245, 249, 239))
        seed.putpixel((seed.width - 1, seed.height - 1), (237, 243, 230))
        return estimated_background(seed, "bilinear-corners")

    def test_gpu_green_gradient_is_not_foreground(self) -> None:
        image = self._gpu_green_gradient()
        self.assertIsNone(content_bbox(image, tolerance=3, background_model="bilinear-corners"))

    def test_real_content_touching_gradient_edge_still_fails(self) -> None:
        image = self._gpu_green_gradient()
        ImageDraw.Draw(image).rectangle((0, 30, 22, 70), fill="#1A1A1A")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "edge.png"
            image.save(path)
            report = audit(path, margin=12, tolerance=3, background_model="bilinear-corners")
        self.assertTrue(report["clipping_risk"])
        self.assertEqual(report["edge_distances"]["left"], 0)


if __name__ == "__main__":
    unittest.main()
