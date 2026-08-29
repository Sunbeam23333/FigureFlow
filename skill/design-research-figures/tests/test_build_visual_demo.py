from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from build_visual_demo import generate_source_data, materialize_data_spec  # noqa: E402


class BuildVisualDemoTests(unittest.TestCase):
    def test_materialized_data_spec_follows_custom_output_directory(self) -> None:
        template = SKILL_DIR / "demo" / "source" / "data_figure.yaml"
        template_before = template.read_bytes()

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "fresh-demo"
            data_files = generate_source_data(output_dir / "source_data")
            materialized = materialize_data_spec(template, data_files, output_dir)

            self.assertEqual(materialized.parent, output_dir.resolve())
            self.assertEqual(materialized.name, "demo_quantitative_source.yaml")
            spec = yaml.safe_load(materialized.read_text(encoding="utf-8"))
            resolved_csvs = [
                (materialized.parent / panel["csv"]).resolve()
                for panel in spec["panels"]
            ]
            self.assertEqual(resolved_csvs, [path.resolve() for path in data_files])
            self.assertTrue(all(path.is_file() for path in resolved_csvs))
            self.assertTrue(
                all(path.is_relative_to(output_dir.resolve()) for path in resolved_csvs)
            )
            self.assertNotIn("../output/source_data", materialized.read_text(encoding="utf-8"))

        self.assertEqual(template.read_bytes(), template_before)


if __name__ == "__main__":
    unittest.main()
