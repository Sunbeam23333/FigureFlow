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

from demo_core import asset_pipeline, pipeline, planner  # noqa: E402
from demo_core.schemas import FigurePlan, StagePlan  # noqa: E402


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

    def test_online_planner_uses_exact_responses_contract(self) -> None:
        calls: list[dict[str, object]] = []
        response = SimpleNamespace(
            id="resp_test",
            output_parsed=planner.load_preset(),
            usage=SimpleNamespace(input_tokens=12, output_tokens=34),
        )
        fake = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: calls.append(kwargs) or response))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}, clear=True), patch.object(
            planner, "OpenAI", return_value=fake
        ):
            _, metadata = planner.plan_figure("测试输入", mode="online")
        self.assertEqual(metadata.model, "gpt-5.6-sol")
        self.assertEqual(calls[0]["model"], "gpt-5.6-sol")
        self.assertEqual(calls[0]["reasoning"], {"effort": "medium"})
        self.assertIs(calls[0]["store"], False)

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


class PipelineTests(unittest.TestCase):
    def test_offline_pipeline_is_portable_and_qa_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            pipeline, "OUTPUT_ROOT", Path(temporary)
        ), patch.dict(os.environ, {"FIGUREFLOW_MAX_RUNS": "2"}, clear=False):
            result = pipeline.run_pipeline("任意输入", mode="offline")
            run_dir = Path(result.run_dir)
            self.assertTrue(result.qa["ok"])
            self.assertTrue(all(item["ok"] for item in result.qa["by_layout"].values()))
            self.assertIn("当前输入未参与语义规划", result.notice)
            self.assertGreater(result.metrics["packaging_ms"], 0)
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
