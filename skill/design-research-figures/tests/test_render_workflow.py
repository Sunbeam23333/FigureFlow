from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from render_workflow import fallback_icon, get_positions, load_theme, stage_card, validate_plan  # noqa: E402


class WorkflowRendererTests(unittest.TestCase):
    def _valid_plan(self) -> dict[str, object]:
        return {
            "title": "Reference validation workflow",
            "takeaway": "Reference metadata remains portable and auditable.",
            "layout_family": "ribbon",
            "layout_preset": "standard",
            "theme": "academic-audit",
            "reference_assets": [],
            "evidence_status": "synthetic-demo",
            "status_label": "Synthetic demo",
            "stages": [
                {
                    "title": "Input",
                    "subtitle": "Collect metadata",
                    "body": [],
                    "accent": "blue",
                    "asset_key": "data",
                    "evidence_status": "synthetic-demo",
                },
                {
                    "title": "Validate",
                    "subtitle": "Check source fields",
                    "body": [],
                    "accent": "teal",
                    "asset_key": "process",
                    "evidence_status": "synthetic-demo",
                },
                {
                    "title": "Deliver",
                    "subtitle": "Write safe manifest",
                    "body": [],
                    "accent": "orange",
                    "asset_key": "output",
                    "evidence_status": "synthetic-demo",
                },
            ],
            "gates": [],
            "caption": "Synthetic validation fixture; it establishes no business result.",
            "warnings": [],
        }

    def test_generic_fallback_cross_uses_vertical_center(self) -> None:
        svg = fallback_icon("process", 100, 240, "#2A6FBB")
        self.assertIn("M 100.0 184.0 V 296.0", svg)
        self.assertNotIn("V 156.0", svg)

    def test_presentation_spacious_long_chinese_is_in_bounds_for_every_layout(self) -> None:
        theme = load_theme("gpu-green-tech")
        stages = [
            {
                "title": f"阶段{index}超长中文标题测试",
                "subtitle": "用于投屏验证的超长中文副标题",
                "body": ["这是第一个完整中文正文行", "这是第二个完整中文正文行"],
                "accent": accent,
                "asset_key": key,
                "evidence_status": "synthetic-demo",
            }
            for index, (accent, key) in enumerate(
                zip(
                    ("navy", "blue", "teal", "orange", "violet"),
                    ("data", "process", "decision", "store", "output"),
                ),
                start=1,
            )
        ]
        with tempfile.TemporaryDirectory() as temporary:
            asset_dir = Path(temporary)
            for family in ("ribbon", "bowtie", "dual-rail"):
                reports = []
                for index, (stage, box) in enumerate(zip(stages, get_positions(family, len(stages))), start=1):
                    _, report = stage_card(
                        stage,
                        index,
                        box,
                        asset_dir,
                        theme=theme,
                        layout_preset="presentation-spacious",
                    )
                    reports.append(report)
                self.assertTrue(all(report["horizontal_ok"] for report in reports), family)
                self.assertTrue(all(report["vertical_ok"] for report in reports), family)
                self.assertGreaterEqual(min(report["title_font_size"] for report in reports), 27.5)
                self.assertGreaterEqual(min(report["subtitle_font_size"] for report in reports), 18.75)

    def test_provider_search_requires_source_page_and_license(self) -> None:
        plan = self._valid_plan()
        plan["reference_assets"] = [
            {
                "id": "wm-example",
                "title": "Example reference",
                "uri": "https://upload.wikimedia.org/example.png",
                "source_type": "provider-search",
                "provider": "wikimedia-commons",
                "media_type": "image",
                "source_url": "https://commons.wikimedia.org/wiki/File:Example.png",
            }
        ]
        with self.assertRaisesRegex(ValueError, "license_name"):
            validate_plan(plan)

        plan["reference_assets"][0]["license_name"] = "Public domain"
        validate_plan(plan)

    def test_reference_metadata_rejects_unknown_secret_fields(self) -> None:
        plan = self._valid_plan()
        plan["reference_assets"] = [
            {
                "id": "user-example",
                "title": "User reference",
                "uri": "https://example.org/reference.png",
                "source_type": "user-url",
                "provider": "user-url",
                "media_type": "image",
                "source_url": "https://example.org/reference.png",
                "access_token": "DO_NOT_PERSIST",
            }
        ]
        with self.assertRaisesRegex(ValueError, "unsupported fields") as raised:
            validate_plan(plan)
        self.assertNotIn("DO_NOT_PERSIST", str(raised.exception))

    def test_reference_metadata_rejects_query_or_fragment_in_every_url_field(self) -> None:
        base_asset = {
            "id": "user-example",
            "title": "User reference",
            "uri": "https://example.org/reference.png",
            "source_type": "user-url",
            "provider": "user-url",
            "media_type": "image",
            "source_url": "https://example.org/source",
            "license_url": "https://example.org/license",
        }
        unsafe_values = {
            "uri": "https://example.org/reference.png?token=DO_NOT_PERSIST",
            "source_url": "https://example.org/source#private-section",
            "license_url": "https://example.org/license?session=DO_NOT_PERSIST",
        }
        for field, value in unsafe_values.items():
            with self.subTest(field=field):
                plan = self._valid_plan()
                plan["reference_assets"] = [{**base_asset, field: value}]
                with self.assertRaisesRegex(ValueError, "query string or fragment") as raised:
                    validate_plan(plan)
                self.assertNotIn("DO_NOT_PERSIST", str(raised.exception))

    def test_cli_rejects_signed_reference_url_without_persisting_it(self) -> None:
        plan = self._valid_plan()
        secret_marker = "DO_NOT_PERSIST_123"
        plan["reference_assets"] = [
            {
                "id": "user-example",
                "title": "User reference",
                "uri": f"https://example.org/reference.png?token={secret_marker}#crop",
                "source_type": "user-url",
                "provider": "user-url",
                "media_type": "image",
                "source_url": "https://example.org/reference.png",
            }
        ]
        with self.assertRaisesRegex(ValueError, "query string or fragment"):
            validate_plan(plan)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            asset_dir = root / "assets"
            output_dir = root / "output"
            asset_dir.mkdir()
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "render_workflow.py"),
                    str(plan_path),
                    "--asset-dir",
                    str(asset_dir),
                    "--output-dir",
                    str(output_dir),
                    "--output-name",
                    "unsafe_reference",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn(secret_marker, completed.stdout + completed.stderr)
            self.assertFalse((output_dir / "unsafe_reference_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
