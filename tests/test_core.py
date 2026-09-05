from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_core import asset_pipeline, pipeline, planner, reference_search, renderer_adapter  # noqa: E402
from demo_core.schemas import FigurePlan, StagePlan, display_units  # noqa: E402


class SchemaAndApiTests(unittest.TestCase):
    def test_preset_and_evidence_contract(self) -> None:
        preset = planner.load_preset()
        self.assertEqual(preset.evidence_status, "synthetic-demo")
        payload = preset.model_dump()
        payload["stages"][1]["asset_key"] = payload["stages"][0]["asset_key"]
        with self.assertRaises(ValidationError):
            FigurePlan.model_validate(payload)
        payload = preset.model_dump()
        payload["evidence_status"] = "measured"
        with self.assertRaises(ValidationError):
            FigurePlan.model_validate(payload)
        payload = preset.model_dump()
        payload["stages"][0]["subtitle"] = "这是一个明显超过卡片预算的中文阶段副标题"
        with self.assertRaises(ValidationError):
            FigurePlan.model_validate(payload)
        payload = preset.model_dump()
        payload["stages"][0]["body"] = ["这是一条超过十二个中文字符的正文说明"]
        with self.assertRaises(ValidationError):
            FigurePlan.model_validate(payload)
        payload = preset.model_dump()
        payload["layout_preset"] = "presentation-spacious"
        payload["theme"] = "gpu-green-tech"
        payload["stages"][0]["body"] = ["第一条", "第二条", "第三条"]
        with self.assertRaises(ValidationError):
            FigurePlan.model_validate(payload)

    def test_online_planner_uses_exact_responses_contract(self) -> None:
        calls: list[dict[str, object]] = []
        model_plan_payload = planner.load_preset().model_dump()
        model_plan_payload["reference_assets"] = [
            reference_search.search_references("", provider="offline-example", limit=1)[0].model_dump()
        ]
        response = SimpleNamespace(
            id="resp_test",
            output_parsed=FigurePlan.model_validate(model_plan_payload),
            usage=SimpleNamespace(input_tokens=12, output_tokens=34),
        )
        fake = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: calls.append(kwargs) or response))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}, clear=True), patch.object(
            planner, "OpenAI", return_value=fake
        ):
            planned, metadata = planner.plan_figure("测试输入", mode="online")
        self.assertEqual(metadata.model, "gpt-5.6-sol")
        self.assertEqual(calls[0]["model"], "gpt-5.6-sol")
        self.assertEqual(calls[0]["reasoning"], {"effort": "medium"})
        self.assertIs(calls[0]["store"], False)
        self.assertEqual(planned.reference_assets, [])

    def test_live_icon_tool_call_is_mocked_and_prompt_is_hashed(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "#FF00FF").save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        calls: list[dict[str, object]] = []
        response = SimpleNamespace(
            id="resp_image",
            output=[SimpleNamespace(type="image_generation_call", result=encoded)],
        )
        fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response))
        stage = StagePlan(
            title="数据输入",
            subtitle="读取结构化数据",
            asset_key="data",
            evidence_status="illustrative",
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-only"}, clear=True
        ), patch.object(asset_pipeline, "OpenAI", return_value=fake):
            metadata = asset_pipeline.generate_live_icon(stage, Path(temporary) / "icon.png")
        self.assertEqual(calls[0]["model"], "gpt-5.6-sol")
        self.assertEqual(calls[0]["tool_choice"], {"type": "image_generation"})
        self.assertNotIn("prompt", metadata)
        self.assertEqual(len(str(metadata["prompt_sha256"])), 64)
        self.assertEqual(metadata["border_normalized_px"], 0)

    def test_live_chroma_profile_clears_generated_canvas_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "live.png"
            processed = Path(temporary) / "processed.png"
            manifest = Path(temporary) / "manifest.json"
            image = Image.new("RGB", (128, 128), "#FF00FF")
            image.putpixel((0, 0), (255, 0, 230))
            for x in range(32, 96):
                for y in range(32, 96):
                    image.putpixel((x, y), (30, 90, 180))
            image.save(raw)
            self.assertEqual(asset_pipeline.normalize_chroma_border(raw), 12)
            asset_pipeline.process_asset(raw, processed, manifest, live_generated=True)
            with Image.open(processed) as result:
                alpha = result.convert("RGBA").getchannel("A")
                corners = (
                    alpha.getpixel((0, 0)),
                    alpha.getpixel((alpha.width - 1, 0)),
                    alpha.getpixel((0, alpha.height - 1)),
                    alpha.getpixel((alpha.width - 1, alpha.height - 1)),
                )
            self.assertEqual(corners, (0, 0, 0, 0))


class PipelineTests(unittest.TestCase):
    def test_spacious_override_compacts_three_line_model_body_with_audit_source(self) -> None:
        source_plan, planning = planner.plan_figure("模型返回三行正文", mode="offline")
        payload = source_plan.model_dump()
        original_body = ["保留原始输入语义", "提取核心节点关系", "补充边界与证据"]
        payload["layout_preset"] = "standard"
        payload["stages"][0]["body"] = original_body
        model_plan = FigurePlan.model_validate(payload)

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            pipeline, "OUTPUT_ROOT", Path(temporary)
        ), patch.object(pipeline, "plan_figure", return_value=(model_plan, planning)):
            result = pipeline.run_pipeline(
                "模型返回三行正文",
                mode="online",
                layout_preset_override="presentation-spacious",
            )

        compacted = result.plan["stages"][0]["body"]
        self.assertEqual(result.plan["layout_preset"], "presentation-spacious")
        self.assertEqual(compacted[0], original_body[0])
        self.assertEqual(len(compacted), 2)
        self.assertTrue(all(display_units(line) <= 24 for line in compacted))
        self.assertIn("提取", compacted[1])
        self.assertIn("补充", compacted[1])
        self.assertEqual(
            result.plan["warnings"][0],
            f"投屏压缩原文[{model_plan.stages[0].title}]：{original_body[1]}｜{original_body[2]}",
        )
        self.assertIn(source_plan.warnings[0], result.plan["warnings"])
        self.assertTrue(result.qa["ok"])

    def test_offline_pipeline_is_portable_and_qa_clean(self) -> None:
        references = reference_search.search_references("", provider="offline-example", limit=1)
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            pipeline, "OUTPUT_ROOT", Path(temporary)
        ), patch.dict(os.environ, {"FIGUREFLOW_MAX_RUNS": "2"}, clear=False):
            result = pipeline.run_pipeline(
                "任意输入",
                mode="offline",
                layout_preset_override="presentation-spacious",
                theme_override="gpu-green-tech",
                reference_assets=references,
                reference_import_ids=[references[0].id],
                reference_visual_id=references[0].id,
            )
            run_dir = Path(result.run_dir)
            self.assertTrue(result.qa["ok"])
            self.assertTrue(all(item["ok"] for item in result.qa["by_layout"].values()))
            self.assertIn("当前输入未参与语义规划", result.notice)
            self.assertGreater(result.metrics["packaging_ms"], 0)
            self.assertGreaterEqual(result.metrics["reference_import_ms"], 0)
            self.assertGreaterEqual(result.metrics["total_ms"], result.metrics["qa_ms"])
            self.assertLess(Path(result.bundle_zip).stat().st_size, 25 * 1024 * 1024)
            forbidden = str(ROOT.parent)
            for path in run_dir.rglob("*.json"):
                self.assertNotIn(forbidden, path.read_text(encoding="utf-8"))
            with zipfile.ZipFile(result.bundle_zip) as archive:
                manifest = archive.read("run_manifest.json").decode("utf-8")
                self.assertNotIn(forbidden, manifest)
                self.assertIn('"packaging_ms"', manifest)
            svg = Path(result.final_svg).read_text(encoding="utf-8")
            self.assertIn('id="stage-01"', svg)
            self.assertIn("提效比例必须通过", svg)
            self.assertIn('data-theme="gpu-green-tech"', svg)
            self.assertIn('data-layout-preset="presentation-spacious"', svg)
            self.assertIn("#63B246", svg)
            self.assertEqual(result.plan["reference_assets"][0]["provider"], "offline-example")
            self.assertEqual(result.reference_imports[0]["id"], "offline-figureflow-workflow")
            self.assertTrue(Path(result.reference_previews[0]).is_file())
            self.assertEqual(result.qa["reference_imports"][0]["provider"], "offline-example")
            self.assertEqual(result.qa["reference_imports"][0]["source_path"], "references/offline-figureflow-workflow/source.png")
            first_asset_manifest = json.loads(
                (run_dir / "assets" / "manifests" / "layout_planner.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first_asset_manifest["source_type"], "validated-public-reference")
            self.assertEqual(first_asset_manifest["source_reference_id"], "offline-figureflow-workflow")
            self.assertIn(
                first_asset_manifest["processing"]["background_removal_mode"],
                {"local-uniform-border-soft-matte", "none-complex-background-preserved"},
            )
            self.assertTrue(
                all(item["layout_qa"]["presentation_scale_ok"] for item in result.qa["by_layout"].values())
            )

    def test_generic_asset_fallback_is_transparent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "data.png"
            processed = Path(temporary) / "processed.png"
            manifest = Path(temporary) / "manifest.json"
            asset_pipeline.create_fallback_asset("data", raw)
            asset_pipeline.process_asset(raw, processed, manifest)
            with Image.open(processed) as image:
                alpha = image.convert("RGBA").getchannel("A")
                self.assertEqual(alpha.getpixel((0, 0)), 0)

    def test_local_reference_cutout_uses_uniform_border_and_never_calls_a_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "reference.png"
            processed = Path(temporary) / "processed.png"
            manifest = Path(temporary) / "manifest.json"
            image = Image.new("RGB", (256, 180), "white")
            for x in range(72, 184):
                for y in range(38, 142):
                    image.putpixel((x, y), (34, 95, 174))
            image.save(raw)
            asset_pipeline.process_reference_asset(raw, processed, manifest)
            record = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertTrue(record["processing"]["background_removed"])
            self.assertEqual(record["processing"]["background_removal_mode"], "local-uniform-border-soft-matte")
            with Image.open(processed) as result:
                alpha = result.convert("RGBA").getchannel("A")
                self.assertEqual(alpha.getpixel((0, 0)), 0)
                self.assertEqual(alpha.getpixel((result.width // 2, result.height // 2)), 255)

    def test_reference_used_in_layout_is_credited_in_every_rendered_format(self) -> None:
        plan_payload = planner.load_preset().model_dump()
        plan_payload["reference_assets"] = [
            {
                "id": "wm-credits",
                "title": "GPU facility",
                "uri": "https://upload.wikimedia.org/wikipedia/commons/a/ab/GPU_facility.png",
                "source_url": "https://commons.wikimedia.org/wiki/File:GPU_facility.png",
                "source_type": "provider-search",
                "provider": "wikimedia-commons",
                "media_type": "image",
                "author": "Example Author",
                "license_name": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "attribution": "Example Author / CC BY-SA 4.0",
                "used_in_layout": True,
            }
        ]
        plan = FigurePlan.model_validate(plan_payload)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
            asset_pipeline.prepare_assets(plan.stages, root)
            outputs = renderer_adapter.render_plan(
                plan_path,
                root / "assets" / "processed",
                root / "rendered",
                "credited_reference",
            )
            svg = Path(outputs["svg"]).read_text(encoding="utf-8")
            self.assertIn("CC BY-SA 4.0", svg)
            self.assertIn("Example Author", svg)
            self.assertIn("Wikimedia Commons", svg)
            self.assertIn("已缩放/裁切", svg)
            self.assertIn('id="reference-attribution"', svg)
            self.assertTrue(Path(outputs["pdf"]).is_file())
            self.assertTrue(Path(outputs["png"]).is_file())
            manifest = json.loads(Path(outputs["manifest"]).read_text(encoding="utf-8"))
            self.assertIn("CC BY-SA 4.0", manifest["visible_reference_attribution"][0])

    def test_bundled_gpu_and_robot_cases_run_through_chroma_cutout(self) -> None:
        stages = [
            StagePlan(
                title="GPU 告警",
                subtitle="检查集群硬件状态",
                asset_key="gpu_server",
                evidence_status="synthetic-demo",
            ),
            StagePlan(
                title="机器人质检",
                subtitle="检查工件视觉质量",
                asset_key="robot_inspection",
                evidence_status="synthetic-demo",
            ),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            results, live = asset_pipeline.prepare_assets(stages, Path(temporary))
            self.assertIsNone(live)
            self.assertEqual({result.source for result in results}, {"bundled-generated-illustration"})
            for result in results:
                with Image.open(result.processed_path) as image:
                    alpha = image.convert("RGBA").getchannel("A")
                    self.assertEqual(alpha.getpixel((0, 0)), 0)
                    self.assertGreater(alpha.getbbox()[2] - alpha.getbbox()[0], image.width // 3)

    def test_chroma_cli_refuses_in_place_overwrite(self) -> None:
        script = ROOT / "skill" / "design-research-figures" / "scripts" / "remove_chroma.py"
        with tempfile.TemporaryDirectory() as temporary:
            image_path = Path(temporary) / "source.png"
            Image.new("RGB", (16, 16), "#FF00FF").save(image_path)
            original = image_path.read_bytes()
            completed = subprocess.run(
                [sys.executable, str(script), str(image_path), str(image_path), "--auto-key", "border"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(image_path.read_bytes(), original)


class PrivacyTests(unittest.TestCase):
    def test_repository_sources_contain_no_local_absolute_path(self) -> None:
        forbidden = ("/" + "Users/", "/" + "private/", "Desktop/" + "School")
        suffixes = {".py", ".md", ".json", ".yaml", ".yml", ".csv", ".toml", ".txt", ".example"}
        for path in ROOT.rglob("*"):
            if not path.is_file() or "demo/output" in path.as_posix() or "__pycache__" in path.parts:
                continue
            if path.suffix not in suffixes and path.name not in {"Dockerfile", ".gitignore", ".dockerignore"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertFalse(any(token in text for token in forbidden), path.as_posix())


if __name__ == "__main__":
    unittest.main()
