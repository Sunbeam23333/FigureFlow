from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gradio as gr

from demo_core import data_ui


def _artifacts(directory: Path, *, reproduction: bool = False) -> dict[str, str]:
    names = {
        "png": "figure.png", "pdf": "figure.pdf", "svg": "figure.svg",
        "report": "report.json", "manifest": "manifest.json",
    }
    if reproduction:
        names.update({"comparison": "comparison.png", "data": "data.csv", "zip": "delivery.zip"})
    result = {}
    for key, name in names.items():
        path = directory / name
        if key == "report":
            path.write_text(json.dumps({"status": "completed", "source": "published"}), encoding="utf-8")
        else:
            path.write_bytes(b"test artifact")
        result[key] = str(path)
    return result


class DataUITests(unittest.TestCase):
    def test_reproduction_uses_lazy_module_and_returns_every_artifact(self):
        runner = Mock(side_effect=lambda directory: _artifacts(directory, reproduction=True))
        module = SimpleNamespace(run_reproduction=runner)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(sys.modules, {"demo_core.alphaedit_reproduction": module}):
                with patch.dict(os.environ, {}, clear=True):
                    status, preview, comparison, downloads, report = data_ui.run_published_reproduction(
                        output_root=root,
                    )
            self.assertIn("已发表图的矢量重建", status)
            self.assertIn("未调用 AI", status)
            self.assertTrue(preview.endswith("figure.png"))
            self.assertTrue(comparison.endswith("comparison.png"))
            self.assertEqual(len(downloads), 8)
            self.assertEqual(report, {"status": "completed", "source": "published"})
            run_dir = runner.call_args.args[0]
            self.assertEqual(run_dir.parent, root.resolve() / "data")
            self.assertRegex(run_dir.name, r"^alphaedit-[a-f0-9]{32}$")
            self.assertTrue(all(Path(path).is_file() for path in downloads))

    def test_each_run_gets_a_new_directory(self):
        runner = Mock(side_effect=lambda directory: _artifacts(directory, reproduction=True))
        with tempfile.TemporaryDirectory() as temporary:
            for _ in range(2):
                data_ui.run_published_reproduction(output_root=temporary, reproduction_runner=runner)
            first, second = [call.args[0] for call in runner.call_args_list]
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir() and second.is_dir())

    def test_output_outside_run_directory_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unrelated = root / "private.pdf"
            unrelated.write_bytes(b"private")

            def runner(directory):
                result = _artifacts(directory, reproduction=True)
                result["pdf"] = str(unrelated)
                return result

            status, preview, comparison, downloads, report = data_ui.run_published_reproduction(
                output_root=root, reproduction_runner=runner,
            )
            self.assertIn("运行目录之外", status)
            self.assertEqual((preview, comparison, downloads), (None, None, []))
            self.assertNotIn(str(unrelated), json.dumps(report))

    def test_missing_required_artifact_does_not_claim_completion(self):
        def runner(directory):
            result = _artifacts(directory, reproduction=True)
            del result["zip"]
            return result

        with tempfile.TemporaryDirectory() as temporary:
            status, _, _, downloads, _ = data_ui.run_published_reproduction(
                output_root=temporary, reproduction_runner=runner,
            )
        self.assertIn("生成结果不完整", status)
        self.assertEqual(downloads, [])

    def test_csv_is_copied_into_run_and_preserves_numerical_input(self):
        renderer = Mock(side_effect=lambda source, directory, **kwargs: _artifacts(directory))
        module = SimpleNamespace(render_annular_chart=renderer)
        content = "metric,method,value\nEfficacy,AlphaEdit,98.9\nEfficacy,ROME,82.4\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            uploads = root / "uploads"
            uploads.mkdir()
            source = uploads / "measurements.csv"
            source.write_text(content, encoding="utf-8")
            with patch.dict(sys.modules, {"demo_core.data_analysis": module}):
                result = data_ui.run_csv_analysis(
                    source, "User chart", "ROME", output_root=root / "outputs",
                    upload_root=uploads, public_demo=False,
                )
            status, preview, comparison, downloads, report = result
            self.assertIn("CSV 数据分析", status)
            self.assertIsNone(comparison)
            copied, directory = renderer.call_args.args
            self.assertEqual(copied, directory / "input.csv")
            self.assertEqual(copied.read_text(encoding="utf-8"), content)
            self.assertEqual(renderer.call_args.kwargs, {"title": "User chart", "focus_method": "ROME"})
            self.assertIn(str(copied), downloads)
            self.assertEqual(len(downloads), 6)
            self.assertTrue(preview.endswith("figure.png"))
            self.assertEqual(report["status"], "completed")

    def test_public_mode_rejects_upload_before_opening_files_or_loading_renderer(self):
        renderer = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(data_ui, "_read_csv_upload", side_effect=AssertionError("read called")):
                with patch.dict(os.environ, {"FIGUREFLOW_PUBLIC_DEMO": "true"}, clear=True):
                    result = data_ui.run_csv_analysis(
                        "not-an-upload.csv", output_root=temporary, chart_renderer=renderer,
                    )
            self.assertFalse((Path(temporary) / "data").exists())
        self.assertIn("公开演示", result[0])
        self.assertEqual(result[3], [])
        renderer.assert_not_called()

    def test_direct_server_path_and_symlink_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            uploads = root / "uploads"
            uploads.mkdir()
            source = root / "server.csv"
            source.write_text("metric,method,value\nx,a,1\n", encoding="utf-8")
            link = uploads / "linked.csv"
            link.symlink_to(source)
            for value in (source, link):
                with self.subTest(value=value.name):
                    renderer = Mock()
                    result = data_ui.run_csv_analysis(
                        value, output_root=root / "out", upload_root=uploads,
                        public_demo=False, chart_renderer=renderer,
                    )
                    self.assertIn("当前页面上传", result[0])
                    renderer.assert_not_called()

    def test_csv_size_type_encoding_and_labels_are_bounded(self):
        cases = (
            ("empty.csv", b"", "Valid", "AlphaEdit", "不能为空"),
            ("large.csv", b"x" * (data_ui.MAX_CSV_BYTES + 1), "Valid", "AlphaEdit", "2 MB"),
            ("wrong.txt", b"x", "Valid", "AlphaEdit", ".csv"),
            ("encoding.csv", b"\xff\xfe", "Valid", "AlphaEdit", "UTF-8"),
            ("title.csv", b"x", "x" * 161, "AlphaEdit", "标题"),
            ("focus.csv", b"x", "Valid", "a\nb", "重点方法"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, content, title, focus, expected in cases:
                with self.subTest(name=name):
                    source = root / name
                    source.write_bytes(content)
                    renderer = Mock()
                    result = data_ui.run_csv_analysis(
                        source, title, focus, output_root=root / "out", upload_root=root,
                        public_demo=False, chart_renderer=renderer,
                    )
                    self.assertIn(expected, result[0])
                    renderer.assert_not_called()
            self.assertFalse((root / "out").exists())

    def test_exception_details_are_not_exposed(self):
        runner = Mock(side_effect=RuntimeError("deployment-private-value"))
        with tempfile.TemporaryDirectory() as temporary:
            result = data_ui.run_published_reproduction(output_root=temporary, reproduction_runner=runner)
        self.assertNotIn("deployment-private-value", str(result))
        self.assertEqual(result[4]["error_type"], "RuntimeError")

    def test_section_builds_without_importing_renderers_and_public_upload_is_disabled(self):
        with patch.dict(sys.modules, {"demo_core.alphaedit_reproduction": None, "demo_core.data_analysis": None}):
            with tempfile.TemporaryDirectory() as temporary:
                with gr.Blocks(analytics_enabled=False) as demo:
                    data_ui.build_data_section(output_root=temporary, public_demo=True)
        components = demo.get_config_file()["components"]
        by_label = {item["props"].get("label"): item["props"] for item in components}
        self.assertIn("数据分析与论文图复现", by_label)
        self.assertFalse(by_label["上传数据 CSV"]["interactive"])
        self.assertFalse(by_label["图标题"]["interactive"])
        self.assertFalse(by_label["重点显示的方法"]["interactive"])


if __name__ == "__main__":
    unittest.main()
