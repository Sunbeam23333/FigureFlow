import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "concord_rec_reference"


class ConcordRecReferenceTests(unittest.TestCase):
    def test_reference_bundle_has_editable_sources_and_vectors(self):
        self.assertTrue((CASE / "sources" / "figure1_architecture_render_v8.py").is_file())
        self.assertTrue((CASE / "sources" / "figure1_style_refinement_revise.py").is_file())
        self.assertTrue((CASE / "sources" / "figure2_network_render_v4.py").is_file())
        for stem in ("architecture", "network_structure"):
            self.assertTrue((CASE / "reference" / f"{stem}.svg").is_file())
            self.assertTrue((CASE / "reference" / f"{stem}.pdf").is_file())
            self.assertTrue((CASE / "reference" / f"{stem}.png").is_file())

    def test_provenance_preserves_status_boundary_and_roles(self):
        payload = json.loads((CASE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["figures"]["figure1"]["status"], "illustrative")
        self.assertEqual(payload["figures"]["figure1"]["base_source_file"], "sources/figure1_architecture_render_v8.py")
        self.assertEqual(payload["figures"]["figure2"]["status"], "illustrative")
        self.assertEqual(payload["palette"]["navy_backbone"], "#183B60")
        self.assertIn("benchmark metric", payload["status_boundary"])


if __name__ == "__main__":
    unittest.main()
