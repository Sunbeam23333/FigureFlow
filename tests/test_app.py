from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from demo_core.pipeline import RunResult  # noqa: E402
from demo_core.schemas import ReferenceAsset  # noqa: E402


class DemoControlTests(unittest.TestCase):
    def _reference(self) -> ReferenceAsset:
        return ReferenceAsset(
            id="wm-11",
            title="GPU cluster",
            uri="https://upload.wikimedia.org/gpu.jpg",
            source_url="https://commons.wikimedia.org/wiki/File:GPU_cluster.jpg",
            source_type="provider-search",
            provider="wikimedia-commons",
            author="CSIRO",
            license_name="CC BY 3.0",
            license_url="https://creativecommons.org/licenses/by/3.0/",
        )

    def test_reference_summary_is_clickable_and_explicitly_metadata_only(self) -> None:
        summary = app._reference_summary([self._reference()])
        self.assertIn("metadata-only", summary)
        self.assertIn("https://commons.wikimedia.org/wiki/File:GPU_cluster.jpg", summary)
        self.assertIn("CC BY 3.0", summary)
        self.assertIn("不会自动下载图片", summary)

    def test_demo_routes_theme_layout_and_reference_metadata_into_pipeline(self) -> None:
        reference = self._reference()
        result = RunResult(
            run_id="test-run",
            run_dir="run",
            plan={"reference_assets": [reference.model_dump()]},
            planning={},
            selected_layout="ribbon",
            candidates=[],
            raw_preview="raw.png",
            processed_preview="processed.png",
            contact_sheet="sheet.png",
            final_png="final.png",
            final_svg="final.svg",
            final_pdf="final.pdf",
            bundle_zip="bundle.zip",
            manifest="manifest.json",
            metrics={
                "planning_ms": 1,
                "icon_generation_ms": 0,
                "cutout_ms": 1,
                "asset_pipeline_ms": 1,
                "render_3_layouts_ms": 1,
                "qa_ms": 1,
                "packaging_ms": 1,
                "total_ms": 5,
            },
            qa={"ok": True},
            notice="离线复演 · QA 通过",
        )
        with patch.object(app, "_resolve_references", return_value=[reference]), patch.object(
            app, "run_pipeline", return_value=result
        ) as run:
            outputs = app._run_demo(
                "GPU brief",
                "离线：稳定复演预设",
                "横向流程 · ribbon",
                "投屏大字 · presentation-spacious",
                "GPU Systems Green（通用非官方）",
                False,
                "Wikimedia Commons（固定接口，仅元数据）",
                "GPU cluster",
                "",
            )
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["theme_override"], "gpu-green-tech")
        self.assertEqual(kwargs["layout_preset_override"], "presentation-spacious")
        self.assertEqual(kwargs["reference_assets"], [reference])
        self.assertIn("GPU cluster", outputs[10])


if __name__ == "__main__":
    unittest.main()
