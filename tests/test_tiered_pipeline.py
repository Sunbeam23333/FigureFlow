from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from demo_core.figure_router import route_figure
from demo_core.schemas import FigureSpec
from demo_core.tiered_pipeline import LAYOUT_ID, load_layout, validate_spec


ROOT = Path(__file__).resolve().parents[1]
CASE_SCRIPT = ROOT / "cases" / "looped_comic_case_studies" / "build_tiered_looped_demo.py"


def load_case_module():
    spec = importlib.util.spec_from_file_location("looped_tiered_demo", CASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load tiered demo")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TieredPipelineTests(unittest.TestCase):
    def test_reference_geometry_is_grid_first_and_orthogonal(self):
        layout = load_layout()
        self.assertEqual(layout["id"], LAYOUT_ID)
        self.assertEqual(layout["canvas"], {"width": 1600, "height": 1298, "margin": 32})
        self.assertEqual(layout["connectors"]["style"], "orthogonal")
        self.assertTrue(layout["connectors"]["avoid_curved_flow_arcs"])
        self.assertEqual(len(layout["tiers"]["top"]), 3)
        self.assertEqual(len(layout["tiers"]["middle"]), 3)

    def test_demo_specs_validate_and_use_three_by_three_modules(self):
        module = load_case_module()
        self.assertEqual(len(module.SPECS), 3)
        for case in module.SPECS:
            self.assertIs(validate_spec(case), case)
            self.assertEqual(len(case["observe"]), 3)
            self.assertEqual(len(case["states"]), 3)

    def test_invalid_spec_is_rejected(self):
        module = load_case_module()
        broken = copy.deepcopy(module.SPECS[0])
        broken["states"] = broken["states"][:2]
        with self.assertRaises(ValueError):
            validate_spec(broken)

    def test_figure_spec_accepts_tiered_pipeline(self):
        spec = FigureSpec(
            figure_id="tiered-demo",
            role="pipeline",
            claim="Parallel evidence branches converge into one trainable state.",
            reading_order=["source", "evidence", "shared", "training"],
            evidence_status="illustrative",
            layout_family="tiered-pipeline",
            target_width_pt=540,
        )
        self.assertEqual(spec.layout_family, "tiered-pipeline")
        route = route_figure(spec)
        self.assertEqual(route["layout_route"]["layout_spec"], "skill/design-research-figures/assets/layouts/tiered_pipeline_reference.json")

    def test_renderer_rebuilds_all_three_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "rendered"
            # Run into an isolated directory so a test never dirties the
            # checked-in primary artifacts or their PDF metadata.
            run = subprocess.run(
                [sys.executable, str(CASE_SCRIPT), "--output-dir", str(output)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            for stem in ("looped_parkour_refine", "looped_robot_active_sensing", "looped_autonomous_vehicle"):
                self.assertTrue((output / f"{stem}.svg").is_file())
                self.assertTrue((output / f"{stem}.pdf").is_file())
                self.assertTrue((output / f"{stem}.png").is_file())
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["layout"], LAYOUT_ID)
            self.assertEqual(len(manifest["figures"]), 3)
