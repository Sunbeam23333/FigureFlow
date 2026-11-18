from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
import sys

sys.path.insert(0, str(SCRIPT_DIR))

from render_data_figure import render  # noqa: E402


class DataFigureRendererTests(unittest.TestCase):
    def test_bubble_errorbars_and_direct_label_render(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "points.csv").write_text(
                "time,fid,params,low,high\n0.1,15.2,1,14.8,15.6\n1.0,9.4,4,9.0,9.8\n10.0,5.8,16,5.4,6.2\n",
                encoding="utf-8",
            )
            spec = {
                "title": "Quality–cost smoke test",
                "evidence_status": "synthetic-demo",
                "status": "SYNTHETIC DEMO",
                "status_kind": "synthetic-demo",
                "output_name": "bubble_smoke",
                "panels": [
                    {
                        "title": "FID vs time",
                        "csv": "points.csv",
                        "x": "time",
                        "y_label": "FID ↓",
                        "x_label": "time (s)",
                        "x_scale": "log",
                        "series": [
                            {
                                "kind": "bubble",
                                "x": "time",
                                "y": "fid",
                                "size_field": "params",
                                "size_scale": 12,
                                "low": "low",
                                "high": "high",
                                "label": "models",
                                "direct_label": "Ours",
                                "color": "#0E9F6E",
                            }
                        ],
                    }
                ],
            }
            spec_path = root / "figure.yaml"
            spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
            pdf, png = render(spec_path, root / "out")
            self.assertTrue(pdf.is_file())
            self.assertTrue(png.is_file())
            self.assertTrue((root / "out" / "bubble_smoke_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
