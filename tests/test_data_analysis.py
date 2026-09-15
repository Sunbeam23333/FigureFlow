"""The local data path must preserve numbers, provenance and honest comparisons."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from demo_core.data_analysis import (
    analysis_markdown, analyze_data, load_data, main, render_annular_chart, render_small_multiples,
)


class DataAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.csv = self.root / "observations.csv"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows, extra=()):
        with self.csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["metric", "method", "value", *extra])
            writer.writerows(rows)
        return self.csv

    def sample(self):
        return self.write([
            ["Accuracy", "Baseline", 60], ["Accuracy", "AlphaEdit", 90],
            ["Latency", "Baseline", 20], ["Latency", "AlphaEdit", 10],
            ["Zero", "Baseline", 0], ["Zero", "AlphaEdit", 0],
        ])

    def test_validate_complete_matrix_preserves_order(self):
        table = load_data(self.sample())
        self.assertEqual(table.metrics, ("Accuracy", "Latency", "Zero"))
        self.assertEqual(table.methods, ("Baseline", "AlphaEdit"))
        self.assertEqual(table.observations[0].evidence_status, "user-supplied")
        self.assertEqual(len(table.sha256), 64)

    def test_rejects_missing_nonfinite_duplicate_and_incomplete(self):
        examples = [
            [["A", "X", ""]], [["A", "X", "nan"]], [["A", "X", "inf"]],
            [["", "X", 1]], [["A", "", 1]], [["A", "X", 1], ["A", "X", 2]],
            [["A", "X", 1], ["A", "Y", 2], ["B", "X", 3]],
        ]
        for rows in examples:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                load_data(self.write(rows))

    def test_rejects_network_and_empty_data(self):
        with self.assertRaises(ValueError):
            load_data("https://example.com/data.csv")
        with self.assertRaises(ValueError):
            load_data(self.write([]))

    def test_numeric_labels_cannot_silently_change_value(self):
        with self.assertRaises(ValueError):
            load_data(self.write([["A", "X", 0.9, "0.95"]], ["label"]))
        table = load_data(self.write([["A", "X", 0.9, "0.90"]], ["label"]))
        self.assertEqual(table.observations[0].label, "0.90")

    def test_direction_relative_comparison_ties_and_zero(self):
        analysis = analyze_data(self.sample(), higher_is_better={"Latency": False})
        accuracy, latency, zero = analysis["metrics"]
        self.assertEqual(accuracy["best_alternative"]["advantage"], 30)
        self.assertEqual(accuracy["best_alternative"]["relative_advantage_pct"], 50)
        self.assertEqual(latency["best_alternative"]["difference"], -10)
        self.assertEqual(latency["best_alternative"]["advantage"], 10)
        self.assertEqual(latency["ranking"][0]["method"], "AlphaEdit")
        self.assertIsNone(zero["best_alternative"]["relative_advantage_pct"])
        self.assertEqual([row["rank"] for row in zero["ranking"]], [1, 1])
        self.assertIsNone(analysis["cross_metric_aggregate"])
        self.assertFalse(analysis["experiment_rerun_by_figureflow"])
        self.assertIn("undefined", analysis_markdown(analysis))

    def test_unknown_focus_or_direction_cannot_silently_fallback(self):
        path = self.sample()
        with self.assertRaises(ValueError):
            analyze_data(path, focus_method="Unknown")
        with self.assertRaises(ValueError):
            analyze_data(path, higher_is_better={"Absent": False})
        with self.assertRaises(ValueError):
            analyze_data(path, higher_is_better={"Accuracy": "False"})

    def test_negative_values_analyzed_without_cross_metric_normalization(self):
        path = self.write([["Loss", "A", -3], ["Loss", "B", -5]])
        report = analyze_data(path, focus_method="B", higher_is_better={"Loss": False})
        self.assertEqual(report["metrics"][0]["best_alternative"]["advantage"], 2)

    def test_comparison_overflow_is_not_exported_as_infinity(self):
        path = self.write([["A", "X", 1e308], ["A", "Y", -1e308]])
        with self.assertRaises(ValueError):
            analyze_data(path)

    def test_best_alternative_excludes_focus_and_reports_ties(self):
        path = self.write([["A", "X", 1], ["A", "Y", 3], ["A", "Z", 3]])
        other = analyze_data(path, focus_method="X")["metrics"][0]["best_alternative"]
        self.assertEqual(other["methods"], ["Y", "Z"])
        self.assertEqual(other["advantage"], -2)

    def test_annular_outputs_are_vector_and_evidence_is_explicit(self):
        path = self.write([
            ["Accuracy", "Baseline", 60, "published-figure"],
            ["Accuracy", "AlphaEdit", 90, "published-figure"],
            ["SST", "Baseline", 0, "published-figure"],
            ["SST", "AlphaEdit", 0.9, "published-figure"],
        ], ["evidence_status"])
        (self.root / "render").mkdir()
        (self.root / "render" / "private-unrelated.txt").write_text("never package this")
        with patch("urllib.request.urlopen", side_effect=AssertionError("Must remain offline")):
            outputs = render_annular_chart(path, self.root / "render", title="Faithful values")
        for kind in ("png", "pdf", "svg", "report", "manifest", "analysis", "data", "zip"):
            self.assertTrue(Path(outputs[kind]).is_file())
        svg = Path(outputs["svg"]).read_text()
        self.assertNotIn("<image", svg)
        self.assertNotIn("<text", svg)
        self.assertIn("<path", svg)
        self.assertIn("published-figure", svg)
        self.assertIn("independently scaled", svg)
        manifest = json.loads(Path(outputs["manifest"]).read_text())
        self.assertTrue(manifest["published_values_present"])
        self.assertFalse(manifest["user_declared_remeasured_values_present"])
        self.assertEqual(manifest["chart"]["metric_maxima"], {"Accuracy": 90, "SST": 0.9})
        self.assertEqual(manifest["chart"]["zero_encoding"], "baseline tick; zero radial length")
        self.assertEqual(Path(outputs["pdf"]).read_bytes()[:5], b"%PDF-")
        copied = load_data(outputs["data"])
        self.assertEqual([row.value for row in copied.observations], [60, 90, 0, 0.9])
        with zipfile.ZipFile(outputs["zip"]) as archive:
            self.assertEqual(len(archive.namelist()), 7)
            self.assertNotIn("private-unrelated.txt", archive.namelist())

    def test_small_multiples_support_signed_values_and_mixed_evidence(self):
        path = self.write([
            ["Effect", "A", -3, "published-table"], ["Effect", "B", 2, "remeasured"],
        ], ["evidence_status"])
        outputs = render_small_multiples(path, self.root / "small")
        manifest = json.loads(Path(outputs["manifest"]).read_text())
        self.assertTrue(manifest["user_declared_remeasured_values_present"])
        self.assertFalse(manifest["experiment_rerun_by_figureflow"])
        self.assertEqual(manifest["chart"]["normalization"], "none; original values")
        svg = Path(outputs["svg"]).read_text()
        self.assertIn("-3 [T]", svg)
        self.assertIn("2 [R]", svg)

    def test_annular_rejects_signed_values_before_creating_outputs(self):
        path = self.write([["A", "X", -3], ["B", "X", 4]])
        with self.assertRaises(ValueError):
            render_annular_chart(path, self.root / "bad")
        self.assertFalse((self.root / "bad").exists())

    def test_cli_uses_same_validated_analysis(self):
        path = self.sample()
        with patch("builtins.print"):
            code = main([str(path), "--output-dir", str(self.root / "cli"),
                         "--chart", "small-multiples", "--lower-is-better", "Latency"])
        self.assertEqual(code, 0)
        report = json.loads((self.root / "cli" / "small_multiples_analysis.json").read_text())
        self.assertEqual(report["metrics"][1]["direction"], "lower")

    def test_cli_kind_alias(self):
        path = self.sample()
        with patch("builtins.print"):
            code = main([str(path), "--output-dir", str(self.root / "alias"),
                         "--kind", "small-multiples"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "alias" / "small_multiples_manifest.json").is_file())

    def test_output_symlinks_rejected_before_any_writes(self):
        path = self.sample()
        protected = self.root / "protected.txt"
        protected.write_text("keep this exact content")
        for filename in ("annular_chart.png", "annular_chart_manifest.json", "annular_chart_bundle.zip"):
            with self.subTest(filename=filename):
                target = self.root / filename.replace(".", "-")
                target.mkdir()
                (target / filename).symlink_to(protected)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    render_annular_chart(path, target)
                self.assertEqual(protected.read_text(), "keep this exact content")
                self.assertEqual([item.name for item in target.iterdir()], [filename])

    def test_source_csv_cannot_be_overwritten_by_normalized_copy(self):
        target = self.root / "source-collision"
        target.mkdir()
        self.csv = target / "annular_chart_data.csv"
        path = self.sample()
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "input CSV"):
            render_annular_chart(path, target)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual([item.name for item in target.iterdir()], [path.name])

    def test_long_center_text_and_methods_fail_with_actionable_guidance(self):
        path = self.sample()
        for kwargs in ({"title": "An overlong title " * 10}, {"subtitle": "A detailed subtitle " * 10}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "shorten"):
                render_annular_chart(path, self.root / "too-long", **kwargs)
        self.assertFalse((self.root / "too-long").exists())
        path = self.write([["A", "A method with an unreasonably long descriptive name", 1],
                           ["B", "A method with an unreasonably long descriptive name", 2]])
        with self.assertRaisesRegex(ValueError, "concise"):
            render_annular_chart(path, self.root / "too-long")

    def test_dense_metric_labels_fail_instead_of_shrinking_below_readable_size(self):
        path = self.write([[f"Long performance metric {index:02}", f"M{method}", method + 1]
                           for index in range(24) for method in range(5)])
        with self.assertRaisesRegex(ValueError, "density"):
            render_annular_chart(path, self.root / "dense")
        self.assertFalse((self.root / "dense").exists())

    def test_long_small_multiple_title_is_wrapped_or_rejected(self):
        path = self.sample()
        with self.assertRaisesRegex(ValueError, "shorten"):
            render_small_multiples(path, self.root / "too-long", title="W" * 160)
        self.assertFalse((self.root / "too-long").exists())


if __name__ == "__main__":
    unittest.main()
