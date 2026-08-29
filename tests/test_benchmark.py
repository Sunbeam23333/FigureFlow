from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "benchmark" / "analyze_results.py"
SPEC = importlib.util.spec_from_file_location("figureflow_benchmark", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def measured_row(
    method: str,
    participant: str,
    order: int,
    *,
    total: float,
    active: float,
    local_edit: float,
    text_errors: int,
) -> dict[str, str]:
    suffix = f"{participant}-{method}"
    return {
        "assignment_id": f"T01-{method}",
        "run_id": suffix,
        "participant_id": participant,
        "reviewer_id": "R01",
        "task_id": "T01",
        "method": method,
        "trial_index": "1",
        "method_order": str(order),
        "measurement_status": "measured",
        "exclusion_reason": "",
        "started_at": "2026-08-29T09:00:00+08:00",
        "ended_at": "2026-08-29T09:20:00+08:00",
        "time_limit_seconds": "1200",
        "total_elapsed_seconds": str(total),
        "first_pass_seconds": str(total),
        "active_work_seconds": str(active),
        "local_edit_seconds": str(local_edit),
        "pipeline_runtime_seconds": "15" if method == "figureflow" else "",
        "semantic_items_total": "10",
        "semantic_items_correct": "10" if method == "figureflow" else "9",
        "text_formula_errors": str(text_errors),
        "layout_defects": "0" if method == "figureflow" else "1",
        "non_target_items_total": "8",
        "non_target_items_unchanged": "8" if method == "figureflow" else "7",
        "interaction_rounds": "1" if method == "figureflow" else "3",
        "editable_delivery": "true",
        "acceptance_pass": "true",
        "reviewer_blinded": "true",
        "evidence_uri": f"evidence/{suffix}.mp4",
        "notes": "",
    }


def write_results(path: Path, rows: list[dict[str, str]]) -> None:
    with (ROOT / "benchmark" / "results_template.csv").open(encoding="utf-8", newline="") as handle:
        fields = csv.DictReader(handle).fieldnames
    assert fields is not None
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class BenchmarkTests(unittest.TestCase):
    def test_empty_template_does_not_create_claims(self) -> None:
        report = benchmark.analyze(
            ROOT / "benchmark" / "results_template.csv",
            ROOT / "benchmark" / "tasks.csv",
        )
        self.assertEqual(report["status"], "no_measured_data")
        self.assertEqual(report["method_summaries"], {})
        self.assertEqual(report["comparisons"], [])

    def test_measured_rows_get_paired_ratios_and_iqr(self) -> None:
        rows = [
            measured_row("manual_docs", "P01", 1, total=300, active=280, local_edit=60, text_errors=2),
            measured_row("whole_image_edit", "P01", 2, total=240, active=200, local_edit=70, text_errors=3),
            measured_row("figureflow", "P01", 3, total=120, active=60, local_edit=20, text_errors=0),
            measured_row("figureflow", "P02", 1, total=120, active=50, local_edit=20, text_errors=0),
            measured_row("manual_docs", "P02", 2, total=360, active=330, local_edit=80, text_errors=1),
            measured_row("whole_image_edit", "P02", 3, total=300, active=240, local_edit=80, text_errors=2),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            results = Path(temporary) / "results.csv"
            write_results(results, rows)
            report = benchmark.analyze(results, ROOT / "benchmark" / "tasks.csv")
        self.assertEqual(report["status"], "ok")
        manual = next(item for item in report["comparisons"] if item["baseline"] == "manual_docs")
        whole = next(item for item in report["comparisons"] if item["baseline"] == "whole_image_edit")
        self.assertEqual(manual["matched_runs"], 2)
        self.assertEqual(manual["ratios"]["total_elapsed_seconds"]["median"], 2.75)
        self.assertEqual(whole["ratios"]["total_elapsed_seconds"]["median"], 2.25)

    def test_invalid_measured_row_is_rejected(self) -> None:
        row = measured_row("figureflow", "P01", 1, total=120, active=60, local_edit=20, text_errors=0)
        row["first_pass_seconds"] = ""
        with tempfile.TemporaryDirectory() as temporary:
            results = Path(temporary) / "invalid.csv"
            write_results(results, [row])
            with self.assertRaises(benchmark.ValidationProblem):
                benchmark.analyze(results, ROOT / "benchmark" / "tasks.csv")


if __name__ == "__main__":
    unittest.main()
