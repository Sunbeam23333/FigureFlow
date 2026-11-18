from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "top_conference_visual_research"


class TopConferenceResearchTests(unittest.TestCase):
    def test_catalog_covers_four_conferences_and_has_source_urls(self) -> None:
        catalog = json.loads((CASE / "catalog.json").read_text(encoding="utf-8"))
        entries = catalog["entries"]
        self.assertGreaterEqual(len(entries), 12)
        self.assertEqual({entry["conference"] for entry in entries}, {"CVPR", "ICML", "NeurIPS", "ICLR"})
        self.assertTrue(all(entry["source_url"].startswith("https://") for entry in entries))
        self.assertTrue(all(entry["layout_family"] and entry["reusable_rules"] for entry in entries))

    def test_palette_has_colorblind_series_and_semantic_roles(self) -> None:
        palette = json.loads((CASE / "palette_tokens.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(palette["colorblind_safe_series"]), 6)
        for role in ("input_or_observation", "representation_or_latent", "action_or_control", "positive_score_or_ours"):
            self.assertIn(role, palette["semantic_roles"])

    def test_bundle_does_not_vendor_paper_screenshots(self) -> None:
        external_images = [
            path
            for path in CASE.rglob("*")
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        self.assertEqual(external_images, [])


if __name__ == "__main__":
    unittest.main()
