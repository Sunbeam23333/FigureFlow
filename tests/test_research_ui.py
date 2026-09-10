from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from demo_core import research_ui


class FakeHarness:
    last_kwargs = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs
        self.run_dir = Path(kwargs["run_dir"])
        self.run_dir.mkdir(parents=True)
        stem = self.run_dir / "renders" / "001-draft"
        stem.parent.mkdir()
        stem.with_suffix(".png").write_bytes(b"png")
        self.candidates = {"draft": {"stem": str(stem)}}

    def run(self):
        return {"status": "draft_only", "stop_reason": "call_budget"}


class PassingHarness(FakeHarness):
    def run(self):
        for name in ("final.png", "final.svg", "final.pdf", "delivery.zip"):
            (self.run_dir / name).write_bytes(b"artifact")
        return {"status": "automated_review_passed", "human_approval": "pending"}


class ResearchUITests(unittest.TestCase):
    def _uploads(self, root: Path):
        source = root / "paper.txt"
        source.write_text("paper", encoding="utf-8")
        image = root / "asset.png"
        image.write_bytes(b"image")
        return source, image

    def test_feature_gate_rejects_public_share_and_unauthenticated_public_bind(self):
        shared = {"FIGUREFLOW_ENABLE_RESEARCH": "true", "GRADIO_SHARE": "true"}
        with patch.dict(os.environ, shared, clear=True):
            self.assertFalse(research_ui.research_enabled(public_demo=False))
        with patch.dict(
            os.environ,
            {"FIGUREFLOW_ENABLE_RESEARCH": "true", "GRADIO_SERVER_NAME": "0.0.0.0"},
            clear=True,
        ):
            self.assertFalse(research_ui.research_enabled(public_demo=False))
        with patch.dict(
            os.environ,
            {
                "FIGUREFLOW_ENABLE_RESEARCH": "true",
                "GRADIO_SERVER_NAME": "0.0.0.0",
                "FIGUREFLOW_BASIC_AUTH_USER": "user",
                "FIGUREFLOW_BASIC_AUTH_PASSWORD": "password",
            },
            clear=True,
        ):
            self.assertTrue(research_ui.research_enabled(public_demo=False))
            self.assertFalse(research_ui.research_enabled(public_demo=True))

    def test_direct_server_path_is_not_accepted_as_an_upload(self):
        with tempfile.TemporaryDirectory() as upload_temp, tempfile.TemporaryDirectory() as elsewhere:
            source = Path(elsewhere) / "paper.txt"
            source.write_text("paper", encoding="utf-8")
            status, _, _, _, _ = research_ui.run_research(
                [source], [], [], "draw", True,
                output_root=elsewhere,
                upload_root=upload_temp,
                enabled=True,
                harness_factory=FakeHarness,
                client_factory=lambda: object(),
            )
            self.assertIn("仅接受本次通过页面上传", status)

    def test_confirmation_required_before_client_or_harness_creation(self):
        called = []
        with tempfile.TemporaryDirectory() as temporary:
            status, previews, final, downloads, details = research_ui.run_research(
                [], [], [], "draw", False,
                output_root=temporary,
                upload_root=temporary,
                enabled=True,
                harness_factory=FakeHarness,
                client_factory=lambda: called.append(True),
            )
        self.assertIn("请先确认", status)
        self.assertEqual((previews, final, downloads, details), ([], None, [], {}))
        self.assertEqual(called, [])

    def test_draft_shows_candidates_but_never_final_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, image = self._uploads(root)
            status, previews, final, downloads, details = research_ui.run_research(
                [source], [image], [], "draw the main mechanism", True,
                output_root=root / "outputs",
                upload_root=root,
                enabled=True,
                harness_factory=FakeHarness,
                client_factory=lambda: object(),
            )
            self.assertIn("仅保留候选草稿", status)
            self.assertEqual(len(previews), 1)
            self.assertIsNone(final)
            self.assertEqual(downloads, [])
            self.assertEqual(details["status"], "draft_only")
            self.assertEqual(FakeHarness.last_kwargs["max_calls"], 24)
            self.assertEqual(FakeHarness.last_kwargs["max_seconds"], 1200)
            self.assertEqual(FakeHarness.last_kwargs["reasoning_effort"], "medium")

    def test_passed_run_exposes_only_expected_final_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _ = self._uploads(root)
            _, _, final, downloads, details = research_ui.run_research(
                [source], [], [], "draw the main mechanism", True,
                output_root=root / "outputs",
                upload_root=root,
                enabled=True,
                harness_factory=PassingHarness,
                client_factory=lambda: object(),
            )
            self.assertTrue(final.endswith("final.png"))
            self.assertEqual(len(downloads), 3)
            self.assertEqual(details["human_approval"], "pending")


if __name__ == "__main__":
    unittest.main()
