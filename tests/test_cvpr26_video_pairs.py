"""Source-free acceptance failures plus opt-in real-paper end-to-end proof."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from cases.cvpr26_video_pairs import review


class VideoProofTests(unittest.TestCase):
    def test_pinned_cvf_editions(self):
        self.assertEqual(set(review.SOURCES), {"track", "rapid"})
        track = json.loads((review.ROOT / "track/template.json").read_text())
        rapid = json.loads((review.ROOT / "rapid/recipe.json").read_text())
        self.assertEqual(track["source_sha256"], review.SOURCES["track"]["sha256"])
        self.assertEqual(rapid["sha256"], review.SOURCES["rapid"]["sha256"])
        self.assertEqual(len(review.probes("rapid")), 15+3+1)
        for spec in review.SOURCES.values():
            self.assertTrue(spec["url"].startswith("https://openaccess.thecvf.com/content/CVPR2026/papers/"))

    def test_local_failure_is_not_hidden_by_white_space(self):
        a = np.full((100, 200, 3), 255, dtype="uint8")
        a[10:15, 22:26] = (255, 0, 0)
        region = {"label": [.10, .08, .2, .2]}
        equal = review.compare_pixels(a, a, region)
        self.assertEqual(equal["equal_rgb_pct"], 100.)
        b = a.copy()
        b[10:15, 22:26] = (0, 255, 0)
        with self.assertRaisesRegex(ValueError, "label"):
            review.compare_pixels(a, b, region)

    def test_failed_second_case_never_publishes_half_an_atlas(self):
        import subprocess
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            self.skipTest("optional PDF runtime")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            failed = subprocess.CalledProcessError(1, "rapid/build.py")
            with patch.object(review, "check_existing"), patch.object(review.shutil, "which", return_value="tex"), \
                 patch.object(review, "audit_case", return_value={}), \
                 patch.object(review.subprocess, "run", side_effect=[None, failed]), \
                 self.assertRaises(subprocess.CalledProcessError):
                review.build(root, root / "proof")
            self.assertEqual(list(root.iterdir()), [])

    def test_preserves_existing_delivery(self):
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            self.skipTest("optional PDF runtime")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "already exists"):
                review.build(root / "missing_sources", root)

    @unittest.skipUnless(os.getenv("FIGUREFLOW_CVPR26_PDFS") and shutil.which("xelatex"),
                         "set FIGUREFLOW_CVPR26_PDFS and install XeLaTeX for the real-paper proof")
    def test_real_two_page_review(self):
        import pymupdf as pdf
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "proof"
            path = review.build(Path(os.environ["FIGUREFLOW_CVPR26_PDFS"]), dest)
            with pdf.open(path) as doc:
                self.assertEqual(len(doc), 2)
                self.assertIn("Edit-by-Track", doc[0].get_text())
                self.assertIn("RAPID", doc[1].get_text())
            record = json.loads((dest / "acceptance.json").read_text())
            self.assertEqual(record["atlas_sha256"], review.digest(path))
            for slug, data in record["cases"].items():
                self.assertEqual(data["candidate_sha256"], review.digest(dest / slug / "reconstruction.pdf"))


if __name__ == "__main__":
    unittest.main()
