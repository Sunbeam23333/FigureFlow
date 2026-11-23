from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from demo_core.mainfigure_registry import get_mainfigure, list_mainfigures, load_mainfigure_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "cases" / "top_conference_visual_research" / "exact_templates" / "replication_registry.json"


class MainFigureRegistryTests(unittest.TestCase):
    def test_registry_covers_allowlisted_exact_templates(self):
        registry = load_mainfigure_registry()
        exact = json.loads((REGISTRY.parent / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {entry["template_id"] for entry in registry["templates"]},
            {entry["template_id"] for entry in exact["templates"]},
        )
        self.assertTrue(all(entry["grammar"]["renderer"] == "native-tikz" for entry in registry["templates"]))

    def test_queries_are_deterministic_and_filter_by_role(self):
        self.assertEqual(get_mainfigure("d4rt_fig1")["source"]["conference"], "CVPR")
        data = list_mainfigures(role="data-analysis")
        self.assertGreaterEqual(len(data), 4)
        self.assertTrue(all(item["grammar"]["role"] == "data-analysis" for item in data))

    def test_cli_emits_compact_success_record(self):
        script = ROOT / "skill" / "design-research-figures" / "scripts" / "validate_mainfigure_registry.py"
        run = subprocess.run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        payload = json.loads(run.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["templates"], 13)


if __name__ == "__main__":
    unittest.main()
