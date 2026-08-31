from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from demo_core.schemas import FigurePlan


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        return list(reader.fieldnames), [dict(row) for row in reader]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


runner = load_script("figureflow_machine_runner", ROOT / "benchmark" / "run_machine_cases.py")
analyzer = load_script("figureflow_machine_analyzer", ROOT / "benchmark" / "analyze_machine_cases.py")


class MachineBenchmarkTests(unittest.TestCase):
    def test_delivery_qa_requires_both_layout_and_output_audit(self) -> None:
        self.assertEqual(
            runner._delivery_qa_components({"layout_qa": {"ok": True}}, {"ok": True}),
            (True, True, True),
        )
        self.assertEqual(
            runner._delivery_qa_components({"layout_qa": {"ok": False}}, {"ok": True}),
            (False, True, False),
        )
        self.assertEqual(
            runner._delivery_qa_components({"layout_qa": {"ok": True}}, {"ok": False}),
            (True, False, False),
        )

    def test_checked_in_cases_validate_and_cover_new_visual_profiles(self) -> None:
        cases = runner.load_cases(ROOT / "benchmark" / "machine_cases.csv")
        plans = {
            case["case_id"]: FigurePlan.model_validate_json(
                (ROOT / case["plan_path"]).read_text(encoding="utf-8")
            )
            for case in cases
        }
        self.assertEqual(len(plans), 5)
        spacious = [plan for plan in plans.values() if plan.layout_preset == "presentation-spacious"]
        self.assertGreaterEqual(len(spacious), 2)
        self.assertEqual(plans["C05"].theme, "gpu-green-tech")
        self.assertEqual(plans["C05"].layout_preset, "presentation-spacious")
        self.assertIn("gpu_server", {stage.asset_key for stage in plans["C05"].stages})
        self.assertIn("robot_inspection", {stage.asset_key for stage in plans["C02"].stages})
        self.assertEqual(plans["C05"].reference_assets[0].license_name, "CC BY 3.0")
        self.assertEqual(plans["C02"].reference_assets[0].license_name, "Public domain")
        self.assertTrue(runner._reference_provenance_matches(plans["C05"]))
        self.assertTrue(runner._reference_provenance_matches(plans["C02"]))
        self.assertTrue(all(plan.evidence_status == "synthetic-demo" for plan in plans.values()))

    def test_checked_in_analysis_binds_plan_profile_layout_qa_and_hashes(self) -> None:
        report = analyzer.analyze(
            ROOT / "benchmark" / "machine_results.csv",
            ROOT / "benchmark" / "machine_cases.csv",
        )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["summary"]["successful_machine_runs"], 5)
        self.assertEqual(report["summary"]["delivery_qa_passes"], 5)
        self.assertEqual(report["summary"]["gpu_green_tech_cases"], 1)
        self.assertEqual(report["human_comparison_benchmark"]["measured"], 0)
        for item in report["case_runs"]:
            machine = item["machine_measurement"]
            self.assertTrue(machine["renderer_layout_qa_pass"])
            self.assertTrue(machine["output_audit_pass"])
            self.assertTrue(machine["delivery_qa_pass"])
            self.assertRegex(machine["source_plan_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(machine["renderer_manifest_sha256"], r"^[0-9a-f]{64}$")
            expected_ratio = round(item["baseline"]["seconds"] / machine["seconds"], 1)
            self.assertEqual(item["relative_lower_bound_multiple"], expected_ratio)
        self.assertFalse(report["case_runs"][0]["baseline"]["same_task_human_timing"])
        self.assertIn("不是团队人效", report["claim_boundary"]["required_note"])

    def test_analysis_rejects_delivery_qa_that_ignores_layout_failure(self) -> None:
        header, rows = read_csv(ROOT / "benchmark" / "machine_results.csv")
        rows[0]["renderer_layout_qa_pass"] = "false"
        with tempfile.TemporaryDirectory(dir=ROOT / "benchmark") as temporary:
            results_path = Path(temporary) / "tampered_results.csv"
            write_csv(results_path, header, rows)
            with self.assertRaises(analyzer.ValidationProblem) as raised:
                analyzer.analyze(results_path, ROOT / "benchmark" / "machine_cases.csv")
        self.assertIn("delivery_qa_pass", str(raised.exception))

    def test_analysis_rejects_current_plan_drift(self) -> None:
        case_header, case_rows = read_csv(ROOT / "benchmark" / "machine_cases.csv")
        source_plan = ROOT / case_rows[0]["plan_path"]
        plan_payload = json.loads(source_plan.read_text(encoding="utf-8"))
        plan_payload["caption"] = str(plan_payload.get("caption", "")) + " [tampered]"
        with tempfile.TemporaryDirectory(dir=ROOT / "benchmark") as temporary:
            temp_dir = Path(temporary)
            drifted_plan = temp_dir / "drifted_plan.json"
            drifted_plan.write_text(
                json.dumps(plan_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            case_rows[0]["plan_path"] = drifted_plan.relative_to(ROOT).as_posix()
            cases_path = temp_dir / "drifted_cases.csv"
            write_csv(cases_path, case_header, case_rows)
            with self.assertRaises(analyzer.ValidationProblem) as raised:
                analyzer.analyze(ROOT / "benchmark" / "machine_results.csv", cases_path)
        self.assertIn("source_plan_sha256", str(raised.exception))

    def test_analysis_rejects_renderer_snapshot_tampering(self) -> None:
        result_header, result_rows = read_csv(ROOT / "benchmark" / "machine_results.csv")
        source_evidence = ROOT / result_rows[0]["evidence_manifest_path"]
        evidence_payload = json.loads(source_evidence.read_text(encoding="utf-8"))
        evidence_payload["renderer_manifest"]["content"]["layout_qa"]["ok"] = False
        with tempfile.TemporaryDirectory(dir=ROOT / "benchmark") as temporary:
            temp_dir = Path(temporary)
            evidence_path = temp_dir / "tampered_evidence.json"
            evidence_path.write_text(
                json.dumps(evidence_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            result_rows[0]["evidence_manifest_path"] = evidence_path.relative_to(ROOT).as_posix()
            results_path = temp_dir / "tampered_results.csv"
            write_csv(results_path, result_header, result_rows)
            with self.assertRaises(analyzer.ValidationProblem) as raised:
                analyzer.analyze(results_path, ROOT / "benchmark" / "machine_cases.csv")
        self.assertIn("渲染 manifest", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
