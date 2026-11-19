from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "top_conference_visual_research" / "exact_templates"


class ExactTemplateRegistryTests(unittest.TestCase):
    def test_requested_templates_are_allowlisted_and_standalone(self) -> None:
        payload = json.loads((CASE / "manifest.json").read_text(encoding="utf-8"))
        entries = payload["templates"]
        expected = {
            "d4rt_fig1", "ovoxel_fig1", "nitrogen_fig1", "gated_attention_fig1",
            "artificial_hivemind_fig1", "superposition_fig1", "met3r_fig5", "see3d_fig2",
            "mixture_of_scores_fig1", "phase_transition_fig1", "scaling_extrapolation_fig1",
            "uncertainty_swarm_fig1",
        }
        self.assertEqual({entry["template_id"] for entry in entries}, expected)
        self.assertTrue(all(entry["source_url"].startswith("https://") for entry in entries))
        for entry in entries:
            source = CASE / entry["template_id"] / "main.tex"
            self.assertTrue(source.is_file(), entry["template_id"])
            self.assertIn("\\documentclass", source.read_text(encoding="utf-8"))

    def test_exact_bundle_does_not_vendor_raster_or_paper_screenshots(self) -> None:
        images = [p for p in CASE.rglob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        self.assertEqual(images, [])

    def test_exact_atlas_is_a_six_page_contact_sheet(self) -> None:
        from pypdf import PdfReader

        atlas = CASE.parent / "figureflow_exact_reproduction_atlas.pdf"
        self.assertTrue(atlas.is_file())
        self.assertEqual(len(PdfReader(str(atlas)).pages), 6)

    def test_renderer_rejects_unknown_template_without_path_access(self) -> None:
        import importlib.util

        script = ROOT / "skill" / "design-research-figures" / "scripts" / "render_exact_template.py"
        spec = importlib.util.spec_from_file_location("render_exact_template", script)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        self.assertEqual(module.render("../main.tex", Path("/tmp/unused"), 90, "xelatex"), 2)


if __name__ == "__main__":
    unittest.main()
