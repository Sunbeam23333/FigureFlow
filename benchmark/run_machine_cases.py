#!/usr/bin/env python3
"""Run checked-in representative plans through the public deterministic delivery chain.

The timer starts immediately before reading and validating one checked-in FigurePlan,
and stops after its delivery ZIP has been closed. Natural-language planning, human
authoring, human semantic review, upload, and presentation editing are outside this
measurement boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo_core.asset_pipeline import create_contact_sheet, prepare_assets, public_asset_records
from demo_core.renderer_adapter import audit_outputs, render_plan
from demo_core.schemas import FigurePlan


DEFAULT_CASES = ROOT / "benchmark" / "machine_cases.csv"
DEFAULT_RESULTS = ROOT / "benchmark" / "machine_results.csv"
DEFAULT_OUTPUT_ROOT = Path(tempfile.gettempdir()) / "figureflow-machine-runs"
DEFAULT_EVIDENCE_OUTPUT = ROOT / "benchmark" / "machine_evidence"
ASSET_PROVENANCE = ROOT / "assets" / "icons" / "provenance.json"
REFERENCE_BOUND_ASSET_KEYS = {"gpu_server", "robot_inspection"}
CASE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{1,15}$")
BOUNDARY_NOTE = (
    "个人自报历史下界与机器链路实测不是同类测量；不是团队人效、不是同题人工计时、"
    "不是节省工时或因果提效结论。"
)

CASE_COLUMNS = (
    "case_id",
    "case_title",
    "scenario",
    "complexity_class",
    "baseline_type",
    "self_reported_baseline_lower_bound_seconds",
    "baseline_source",
    "baseline_scope",
    "plan_path",
    "layout_family",
    "layout_preset",
    "theme",
    "expected_stage_titles",
    "required_output_formats",
    "measurement_scope",
    "evidence_status",
)

RESULT_COLUMNS = (
    "case_id",
    "run_id",
    "measurement_status",
    "started_at",
    "ended_at",
    "runtime_environment",
    "measurement_scope",
    "plan_validation_seconds",
    "asset_prepare_seconds",
    "render_seconds",
    "delivery_qa_seconds",
    "package_seconds",
    "machine_end_to_end_seconds",
    "stage_count",
    "asset_count",
    "reference_asset_count",
    "source_plan_sha256",
    "renderer_manifest_sha256",
    "plan_contract_pass",
    "reference_provenance_pass",
    "asset_gate_pass",
    "render_success",
    "renderer_layout_qa_pass",
    "output_audit_pass",
    "delivery_qa_pass",
    "package_success",
    "required_formats_present",
    "editable_svg_present",
    "machine_run_success",
    "semantic_review_status",
    "output_formats",
    "evidence_manifest_path",
    "artifact_zip_path",
    "artifact_zip_sha256",
    "artifact_zip_bytes",
    "artifact_retention",
    "notes",
)


class MachineCaseError(RuntimeError):
    """Raised when a case definition is invalid or cannot be measured."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _seconds(started: float) -> float:
    return round(perf_counter() - started, 6)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _portable_error(error: Exception) -> str:
    message = f"{type(error).__name__}: {error}"
    message = message.replace(str(ROOT), ".")
    return " ".join(message.split())[:500]


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _resolve_repo_path(value: str, *, label: str) -> Path:
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise MachineCaseError(f"{label} 必须位于仓库内：{value!r}") from exc
    return path


def load_cases(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise MachineCaseError(f"案例表不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise MachineCaseError("案例表没有表头。")
        missing = [column for column in CASE_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise MachineCaseError(f"案例表缺少列：{', '.join(missing)}")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    if not 3 <= len(rows) <= 5:
        raise MachineCaseError("机器案例必须为 3–5 个。")
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        case_id = row["case_id"]
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise MachineCaseError(f"案例表第 {index} 行 case_id 不安全：{case_id!r}")
        if case_id in seen_ids:
            raise MachineCaseError(f"案例表第 {index} 行 case_id 重复：{case_id}")
        seen_ids.add(case_id)
        try:
            baseline = float(row["self_reported_baseline_lower_bound_seconds"])
        except ValueError as exc:
            raise MachineCaseError(f"案例表第 {index} 行个人下界必须是数字。") from exc
        if baseline <= 0:
            raise MachineCaseError(f"案例表第 {index} 行个人下界必须大于 0。")
        if row["measurement_scope"] != "checked_in_plan_to_delivery_package":
            raise MachineCaseError(f"案例表第 {index} 行 measurement_scope 超出当前计时边界。")
        if row["evidence_status"] != "synthetic-demo":
            raise MachineCaseError(f"案例表第 {index} 行必须明确标记 synthetic-demo。")
        plan_path = _resolve_repo_path(row["plan_path"], label="plan_path")
        if not plan_path.is_file():
            raise MachineCaseError(f"案例表第 {index} 行的计划不存在：{row['plan_path']}")
    return rows


def _artifact_record(path: Path, base: Path) -> dict[str, object]:
    return {
        "path": path.resolve().relative_to(base.resolve()).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _load_renderer_manifest(
    manifest_path: Path,
    *,
    plan: FigurePlan,
    plan_sha256: str,
    processed_asset_dir: Path,
    renderer_outputs: dict[str, Path],
) -> dict[str, Any]:
    """Load and bind the renderer manifest to the exact plan, theme, assets and outputs."""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MachineCaseError(f"渲染 manifest 无法读取：{exc}") from exc
    if not isinstance(payload, dict):
        raise MachineCaseError("渲染 manifest 必须是 JSON 对象。")
    expected_profile = {
        "layout_family": plan.layout_family,
        "layout_preset": plan.layout_preset,
        "theme": plan.theme,
    }
    if any(payload.get(key) != value for key, value in expected_profile.items()):
        raise MachineCaseError("渲染 manifest 的布局/主题与当前 FigurePlan 不一致。")
    if payload.get("plan_sha256") != plan_sha256:
        raise MachineCaseError("渲染 manifest 未绑定当前 FigurePlan SHA-256。")

    layout_qa = payload.get("layout_qa")
    if not isinstance(layout_qa, dict) or not isinstance(layout_qa.get("ok"), bool):
        raise MachineCaseError("渲染 manifest 缺少可验证的 layout_qa.ok。")

    theme_name = payload.get("theme_tokens")
    theme_sha256 = payload.get("theme_tokens_sha256")
    if not isinstance(theme_name, str) or Path(theme_name).name != theme_name:
        raise MachineCaseError("渲染 manifest 的主题 token 路径不安全。")
    theme_path = ROOT / "skill" / "design-research-figures" / "assets" / "themes" / theme_name
    if not theme_path.is_file() or _sha256(theme_path) != theme_sha256:
        raise MachineCaseError("渲染 manifest 的主题 token 哈希与当前仓库不一致。")

    output_hashes = payload.get("output_sha256")
    if not isinstance(output_hashes, dict):
        raise MachineCaseError("渲染 manifest 缺少输出哈希。")
    for key in ("svg", "pdf", "png"):
        output_path = renderer_outputs.get(key)
        if output_path is None or output_hashes.get(output_path.name) != _sha256(output_path):
            raise MachineCaseError(f"渲染 manifest 中的 {key.upper()} 哈希与实际输出不一致。")

    manifest_assets = payload.get("assets")
    if not isinstance(manifest_assets, list):
        raise MachineCaseError("渲染 manifest 缺少素材哈希。")
    actual_assets = {
        path.name: _sha256(path)
        for path in processed_asset_dir.glob("*.png")
        if path.is_file()
    }
    declared_assets = {
        str(item.get("file")): str(item.get("sha256"))
        for item in manifest_assets
        if isinstance(item, dict)
    }
    if declared_assets != actual_assets:
        raise MachineCaseError("渲染 manifest 中的素材哈希与当前处理结果不一致。")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _delivery_qa_components(
    renderer_manifest: dict[str, Any], output_audit: dict[str, object]
) -> tuple[bool, bool, bool]:
    layout_qa = renderer_manifest.get("layout_qa")
    layout_ok = isinstance(layout_qa, dict) and layout_qa.get("ok") is True
    output_ok = output_audit.get("ok") is True
    return layout_ok, output_ok, layout_ok and output_ok


def _create_zip(run_dir: Path, zip_path: Path) -> None:
    files = [
        path
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path != zip_path and path.name != "evidence_manifest.json"
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, path.relative_to(run_dir).as_posix())


def _reference_provenance_matches(plan: FigurePlan) -> bool:
    custom_keys = {stage.asset_key for stage in plan.stages}.intersection(REFERENCE_BOUND_ASSET_KEYS)
    if not custom_keys:
        return not plan.reference_assets
    try:
        provenance = json.loads(ASSET_PROVENANCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    source_records = provenance.get("reference_sources", {})
    for key in custom_keys:
        record = source_records.get(f"{key}.png")
        if not isinstance(record, dict):
            return False
        if not any(
            asset.source_url == record.get("source_page")
            and asset.license_name == record.get("license")
            and asset.source_type == "provider-search"
            for asset in plan.reference_assets
        ):
            return False
    return True


def run_case(case: dict[str, str], output_root: Path, evidence_output_dir: Path) -> dict[str, str]:
    case_id = case["case_id"]
    started_at = _utc_now()
    run_id = f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{case_id.lower()}-{uuid.uuid4().hex[:8]}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    total_started = perf_counter()

    timings = {
        "plan_validation_seconds": 0.0,
        "asset_prepare_seconds": 0.0,
        "render_seconds": 0.0,
        "delivery_qa_seconds": 0.0,
        "package_seconds": 0.0,
    }
    flags = {
        "plan_contract_pass": False,
        "reference_provenance_pass": False,
        "asset_gate_pass": False,
        "render_success": False,
        "renderer_layout_qa_pass": False,
        "output_audit_pass": False,
        "delivery_qa_pass": False,
        "package_success": False,
        "required_formats_present": False,
        "editable_svg_present": False,
    }
    stage_count = 0
    asset_count = 0
    asset_records: list[dict[str, object]] = []
    reference_records: list[dict[str, object]] = []
    output_formats: list[str] = []
    notes = ""
    source_plan_sha256 = ""
    renderer_manifest_sha256 = ""
    renderer_manifest_snapshot: dict[str, Any] = {}
    delivery_qa_snapshot: dict[str, Any] = {}
    plan_copy = run_dir / "figure_plan.json"
    contact_sheet = run_dir / "asset_pipeline.png"
    renderer_outputs: dict[str, Path] = {}
    qa_report_path = run_dir / "qa" / "qa_report.json"
    zip_path = run_dir / f"{case_id.lower()}_delivery.zip"
    evidence_manifest_path = run_dir / "evidence_manifest.json"

    try:
        phase_started = perf_counter()
        source_plan_path = _resolve_repo_path(case["plan_path"], label="plan_path")
        plan = FigurePlan.model_validate_json(source_plan_path.read_text(encoding="utf-8"))
        source_plan_sha256 = _sha256(source_plan_path)
        expected_titles = case["expected_stage_titles"].split("|")
        actual_titles = [stage.title for stage in plan.stages]
        flags["plan_contract_pass"] = (
            actual_titles == expected_titles
            and plan.layout_family == case["layout_family"]
            and plan.layout_preset == case["layout_preset"]
            and plan.theme == case["theme"]
            and plan.evidence_status == case["evidence_status"]
        )
        if not flags["plan_contract_pass"]:
            raise MachineCaseError("已写入计划与案例表的标题、布局或证据状态不一致。")
        flags["reference_provenance_pass"] = _reference_provenance_matches(plan)
        if not flags["reference_provenance_pass"]:
            raise MachineCaseError("已写入计划的参考来源与本地语义素材 provenance 不一致。")
        shutil.copy2(source_plan_path, plan_copy)
        stage_count = len(plan.stages)
        reference_records = [asset.model_dump() for asset in plan.reference_assets]
        timings["plan_validation_seconds"] = _seconds(phase_started)

        phase_started = perf_counter()
        assets, live_metadata = prepare_assets(plan.stages, run_dir, live_icon=False)
        if live_metadata is not None:
            raise MachineCaseError("公开可复现实测不得调用在线图像生成。")
        create_contact_sheet(assets, contact_sheet)
        asset_count = len(assets)
        asset_records = public_asset_records(assets, run_dir)
        for record in asset_records:
            for path_field in ("raw_path", "processed_path", "manifest_path"):
                value = record.get(path_field)
                if isinstance(value, str):
                    artifact_path = run_dir / value
                    if artifact_path.is_file():
                        record[path_field.removesuffix("_path") + "_sha256"] = _sha256(artifact_path)
        flags["asset_gate_pass"] = asset_count == stage_count and all(
            Path(item.processed_path).is_file()
            and item.source in {"deterministic-vector-fallback", "bundled-generated-illustration"}
            for item in assets
        )
        if not flags["asset_gate_pass"]:
            raise MachineCaseError("确定性素材或透明边界门禁未通过。")
        timings["asset_prepare_seconds"] = _seconds(phase_started)

        phase_started = perf_counter()
        raw_outputs = render_plan(
            plan_copy,
            run_dir / "assets" / "processed",
            run_dir / "render",
            case_id.lower(),
        )
        renderer_outputs = {key: Path(value) for key, value in raw_outputs.items()}
        flags["render_success"] = all(path.is_file() for path in renderer_outputs.values())
        if not flags["render_success"]:
            raise MachineCaseError("渲染器没有生成完整输出。")
        renderer_manifest_snapshot = _load_renderer_manifest(
            renderer_outputs["manifest"],
            plan=plan,
            plan_sha256=source_plan_sha256,
            processed_asset_dir=run_dir / "assets" / "processed",
            renderer_outputs=renderer_outputs,
        )
        renderer_manifest_sha256 = _sha256(renderer_outputs["manifest"])
        flags["renderer_layout_qa_pass"] = renderer_manifest_snapshot["layout_qa"]["ok"] is True
        timings["render_seconds"] = _seconds(phase_started)

        phase_started = perf_counter()
        qa = audit_outputs(renderer_outputs["png"], renderer_outputs["pdf"], run_dir / "qa")
        (
            flags["renderer_layout_qa_pass"],
            flags["output_audit_pass"],
            flags["delivery_qa_pass"],
        ) = _delivery_qa_components(
            renderer_manifest_snapshot,
            qa,
        )
        delivery_qa_snapshot = {
            "renderer_layout_qa_ok": flags["renderer_layout_qa_pass"],
            "output_audit_ok": flags["output_audit_pass"],
            "combined_ok": flags["delivery_qa_pass"],
            "output_audit_report": qa,
        }
        timings["delivery_qa_seconds"] = _seconds(phase_started)

        context_path = run_dir / "run_context.json"
        _write_json(
            context_path,
            {
                "schema_version": 1,
                "case_id": case_id,
                "case_title": case["case_title"],
                "run_id": run_id,
                "started_at": _iso_z(started_at),
                "measurement_scope": case["measurement_scope"],
                "excluded_from_timer": [
                    "natural_language_planning",
                    "human_plan_authoring",
                    "reference_search",
                    "initial_semantic_asset_generation",
                    "human_semantic_review",
                    "upload",
                    "presentation_editing",
                ],
                "semantic_review_status": "not_measured",
                "evidence_status": case["evidence_status"],
                "render_profile": {
                    "layout_family": case["layout_family"],
                    "layout_preset": case["layout_preset"],
                    "theme": case["theme"],
                },
                "reference_assets": reference_records,
                "asset_sources": asset_records,
                "boundary_note": BOUNDARY_NOTE,
            },
        )

        phase_started = perf_counter()
        _create_zip(run_dir, zip_path)
        flags["package_success"] = zip_path.is_file() and zipfile.is_zipfile(zip_path)
        required = set(case["required_output_formats"].split("|"))
        present = {
            key for key in ("svg", "pdf", "png", "manifest") if key in renderer_outputs and renderer_outputs[key].is_file()
        }
        if flags["package_success"]:
            present.add("zip")
        output_formats = sorted(present)
        flags["required_formats_present"] = required.issubset(present)
        flags["editable_svg_present"] = "svg" in present
        timings["package_seconds"] = _seconds(phase_started)
    except Exception as exc:  # Preserve failed measurements instead of silently dropping them.
        notes = _portable_error(exc)

    ended_at = _utc_now()
    machine_end_to_end_seconds = _seconds(total_started)
    flags["machine_run_success"] = all(flags.values())
    if not flags["machine_run_success"] and not notes:
        failed_checks = [key for key, passed in flags.items() if not passed and key != "machine_run_success"]
        notes = "failed_checks=" + "|".join(failed_checks)

    artifact_paths = [
        path
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path != evidence_manifest_path
    ]
    _write_json(
        evidence_manifest_path,
        {
            "schema_version": 2,
            "case_id": case_id,
            "case_title": case["case_title"],
            "run_id": run_id,
            "measurement_status": "measured",
            "started_at": _iso_z(started_at),
            "ended_at": _iso_z(ended_at),
            "runtime_environment": f"{platform.system()}-{platform.machine()}; Python {platform.python_version()}",
            "measurement_scope": case["measurement_scope"],
            "timer_definition": (
                "Read and validate checked-in FigurePlan through generic fallback creation or bundled semantic "
                "asset loading, cutout, render, automated delivery QA, required-format check, and closed ZIP."
            ),
            "excluded_from_timer": [
                "natural_language_planning",
                "human_plan_authoring",
                "reference_search",
                "initial_semantic_asset_generation",
                "human_semantic_review",
                "upload",
                "presentation_editing",
                "writing_this_evidence_manifest",
            ],
            "timings_seconds": {**timings, "machine_end_to_end_seconds": machine_end_to_end_seconds},
            "checks": flags,
            "semantic_review_status": "not_measured",
            "evidence_status": case["evidence_status"],
            "input_plan": {
                "path": case["plan_path"],
                "sha256": source_plan_sha256,
            },
            "render_profile": {
                "layout_family": case["layout_family"],
                "layout_preset": case["layout_preset"],
                "theme": case["theme"],
            },
            "renderer_manifest": {
                "path": (
                    renderer_outputs["manifest"].resolve().relative_to(run_dir.resolve()).as_posix()
                    if renderer_outputs.get("manifest") is not None
                    and renderer_outputs["manifest"].is_file()
                    else ""
                ),
                "sha256": renderer_manifest_sha256,
                "content": renderer_manifest_snapshot,
            },
            "delivery_qa": delivery_qa_snapshot,
            "reference_assets": reference_records,
            "asset_sources": asset_records,
            "output_formats": output_formats,
            "artifacts": [_artifact_record(path, run_dir) for path in artifact_paths],
            "boundary_note": BOUNDARY_NOTE,
            "error": notes or None,
        },
    )
    persisted_manifest_path = evidence_output_dir / f"{run_id}.json"
    persisted_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(evidence_manifest_path, persisted_manifest_path)

    try:
        committed_zip_path = zip_path.resolve().relative_to(ROOT.resolve()).as_posix()
        artifact_retention = "committed"
    except ValueError:
        committed_zip_path = ""
        artifact_retention = "not_committed_size_control" if zip_path.is_file() else "not_created"
    artifact_zip_sha256 = _sha256(zip_path) if zip_path.is_file() else ""
    artifact_zip_bytes = str(zip_path.stat().st_size) if zip_path.is_file() else ""

    return {
        "case_id": case_id,
        "run_id": run_id,
        "measurement_status": "measured",
        "started_at": _iso_z(started_at),
        "ended_at": _iso_z(ended_at),
        "runtime_environment": f"{platform.system()}-{platform.machine()}; Python {platform.python_version()}",
        "measurement_scope": case["measurement_scope"],
        **{key: f"{value:.6f}" for key, value in timings.items()},
        "machine_end_to_end_seconds": f"{machine_end_to_end_seconds:.6f}",
        "stage_count": str(stage_count),
        "asset_count": str(asset_count),
        "reference_asset_count": str(len(reference_records)),
        "source_plan_sha256": source_plan_sha256,
        "renderer_manifest_sha256": renderer_manifest_sha256,
        **{key: _bool(value) for key, value in flags.items()},
        "semantic_review_status": "not_measured",
        "output_formats": "|".join(output_formats),
        "evidence_manifest_path": _portable_path(persisted_manifest_path),
        "artifact_zip_path": committed_zip_path,
        "artifact_zip_sha256": artifact_zip_sha256,
        "artifact_zip_bytes": artifact_zip_bytes,
        "artifact_retention": artifact_retention,
        "notes": notes,
    }


def write_results(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _resolve_cli_path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--results-out", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--evidence-out-dir", type=Path, default=DEFAULT_EVIDENCE_OUTPUT)
    parser.add_argument("--case-id", action="append", help="Only run the named case; repeat as needed.")
    args = parser.parse_args()

    cases_path = _resolve_cli_path(args.cases)
    results_path = _resolve_cli_path(args.results_out)
    output_root = _resolve_cli_path(args.output_root)
    evidence_output_dir = _resolve_cli_path(args.evidence_out_dir)
    try:
        evidence_output_dir.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise MachineCaseError("--evidence-out-dir 必须位于仓库内，以便结果可复核。") from exc
    cases = load_cases(cases_path)
    if args.case_id:
        requested = set(args.case_id)
        cases = [case for case in cases if case["case_id"] in requested]
        missing = sorted(requested.difference(case["case_id"] for case in cases))
        if missing:
            raise MachineCaseError(f"未知 case_id：{', '.join(missing)}")

    rows = [run_case(case, output_root, evidence_output_dir) for case in cases]
    write_results(results_path, rows)
    summary = {
        "measurement_status": "measured",
        "measured_case_runs": len(rows),
        "successful_case_runs": sum(row["machine_run_success"] == "true" for row in rows),
        "results": _portable_path(results_path),
        "boundary_note": BOUNDARY_NOTE,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(row["machine_run_success"] == "true" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
