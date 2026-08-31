#!/usr/bin/env python3
"""Validate machine-case evidence and report strictly separated time sources."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "benchmark" / "machine_cases.csv"
DEFAULT_RESULTS = ROOT / "benchmark" / "machine_results.csv"
DEFAULT_JSON = ROOT / "benchmark" / "machine_analysis.json"
DEFAULT_MARKDOWN = ROOT / "benchmark" / "machine_analysis.md"
HUMAN_TEMPLATE = ROOT / "benchmark" / "results_template.csv"

BOUNDARY_NOTE = (
    "个人自报历史下界与机器链路实测不是同类测量；不是团队人效、不是同题人工计时、"
    "不是节省工时或因果提效结论。"
)
COMPARISON_LABEL = "相对个人自报下界的时间尺度倍率"
CHECK_FIELDS = (
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
)
TIMING_FIELDS = (
    "plan_validation_seconds",
    "asset_prepare_seconds",
    "render_seconds",
    "delivery_qa_seconds",
    "package_seconds",
)
RESULT_COLUMNS = (
    "case_id",
    "run_id",
    "measurement_status",
    "started_at",
    "ended_at",
    "runtime_environment",
    "measurement_scope",
    *TIMING_FIELDS,
    "machine_end_to_end_seconds",
    "stage_count",
    "asset_count",
    "reference_asset_count",
    "source_plan_sha256",
    "renderer_manifest_sha256",
    *CHECK_FIELDS,
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


class ValidationProblem(Exception):
    """Raised when persisted evidence is incomplete or internally inconsistent."""

    def __init__(self, errors: Sequence[str]):
        super().__init__("\n".join(errors))
        self.errors = list(errors)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_repo_path(value: str, errors: list[str], location: str) -> Path | None:
    if not value:
        errors.append(f"{location} 的仓库路径不能为空。")
        return None
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        errors.append(f"{location} 的仓库路径越界：{value!r}。")
        return None
    if not path.is_file():
        errors.append(f"{location} 的文件不存在：{value!r}。")
        return None
    return path


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise ValidationProblem([f"文件不存在：{path}"])
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValidationProblem([f"CSV 没有表头：{path}"])
        rows: list[dict[str, str]] = []
        for row_number, raw in enumerate(reader, start=2):
            if None in raw:
                raise ValidationProblem([f"{path}:{row_number} 的字段数多于表头。"])
            row = {key: (value or "").strip() for key, value in raw.items()}
            row["_row_number"] = str(row_number)
            rows.append(row)
    return list(reader.fieldnames), rows


def _resolve_evidence_path(value: str, errors: list[str], location: str) -> Path | None:
    if not value:
        errors.append(f"{location} 的证据路径不能为空。")
        return None
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        errors.append(f"{location} 的证据路径必须位于仓库内：{value!r}。")
        return None
    if not path.is_file():
        errors.append(f"{location} 的证据文件不存在：{value!r}。")
        return None
    return path


def _parse_float(value: str, field: str, location: str, errors: list[str], *, positive: bool) -> float | None:
    try:
        number = float(value)
    except ValueError:
        errors.append(f"{location} 的 {field} 必须是数字。")
        return None
    if not math.isfinite(number):
        errors.append(f"{location} 的 {field} 必须是有限数字。")
        return None
    if positive and number <= 0:
        errors.append(f"{location} 的 {field} 必须大于 0。")
    if not positive and number < 0:
        errors.append(f"{location} 的 {field} 不能小于 0。")
    return number


def _parse_int(
    value: str,
    field: str,
    location: str,
    errors: list[str],
    *,
    positive: bool = True,
) -> int | None:
    number = _parse_float(value, field, location, errors, positive=positive)
    if number is None:
        return None
    if not number.is_integer():
        errors.append(f"{location} 的 {field} 必须是整数。")
        return None
    return int(number)


def _parse_bool(value: str, field: str, location: str, errors: list[str]) -> bool | None:
    lowered = value.lower()
    if lowered not in {"true", "false"}:
        errors.append(f"{location} 的 {field} 只能填写 true 或 false。")
        return None
    return lowered == "true"


def _parse_timestamp(value: str, field: str, location: str, errors: list[str]) -> datetime | None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        errors.append(f"{location} 的 {field} 不是有效 ISO 8601 时间。")
        return None
    if timestamp.tzinfo is None:
        errors.append(f"{location} 的 {field} 必须包含时区。")
    return timestamp


def _load_cases(path: Path) -> dict[str, dict[str, Any]]:
    header, rows = _read_csv(path)
    required = {
        "case_id",
        "case_title",
        "scenario",
        "complexity_class",
        "self_reported_baseline_lower_bound_seconds",
        "baseline_source",
        "baseline_scope",
        "plan_path",
        "measurement_scope",
        "required_output_formats",
        "layout_family",
        "layout_preset",
        "theme",
        "expected_stage_titles",
        "evidence_status",
    }
    errors = [f"案例表缺少列：{', '.join(sorted(required.difference(header)))}"] if not required.issubset(header) else []
    if errors:
        raise ValidationProblem(errors)
    cases: dict[str, dict[str, Any]] = {}
    for row in rows:
        location = f"案例表第 {row['_row_number']} 行"
        case_id = row["case_id"]
        if not case_id:
            errors.append(f"{location} 的 case_id 不能为空。")
            continue
        if case_id in cases:
            errors.append(f"{location} 的 case_id={case_id!r} 重复。")
        baseline = _parse_float(
            row["self_reported_baseline_lower_bound_seconds"],
            "self_reported_baseline_lower_bound_seconds",
            location,
            errors,
            positive=True,
        )
        if row["evidence_status"] != "synthetic-demo":
            errors.append(f"{location} 必须明确标记 synthetic-demo。")
        plan_path = _resolve_repo_path(row["plan_path"], errors, location)
        plan_payload: dict[str, Any] | None = None
        plan_sha256 = ""
        if plan_path is not None:
            try:
                loaded_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{location} 的 FigurePlan 无法读取：{exc}。")
            else:
                if not isinstance(loaded_plan, dict):
                    errors.append(f"{location} 的 FigurePlan 必须是 JSON 对象。")
                else:
                    plan_payload = loaded_plan
                    plan_sha256 = _sha256(plan_path)
                    for field in ("layout_family", "layout_preset", "theme", "evidence_status"):
                        if plan_payload.get(field) != row[field]:
                            errors.append(f"{location} 的 FigurePlan.{field} 与案例表不一致。")
                    stages = plan_payload.get("stages")
                    actual_titles = (
                        [str(stage.get("title", "")) for stage in stages if isinstance(stage, dict)]
                        if isinstance(stages, list)
                        else []
                    )
                    if actual_titles != row["expected_stage_titles"].split("|"):
                        errors.append(f"{location} 的 FigurePlan 节点标题与案例表不一致。")
        if baseline is not None:
            cases[case_id] = {
                **row,
                "baseline_seconds": baseline,
                "plan_payload": plan_payload,
                "plan_sha256": plan_sha256,
            }
    if not 3 <= len(cases) <= 5:
        errors.append("案例表必须包含 3–5 个有效案例。")
    if errors:
        raise ValidationProblem(errors)
    return cases


def _validate_manifest(
    path: Path,
    *,
    case: dict[str, Any],
    case_id: str,
    run_id: str,
    elapsed: float,
    timings: dict[str, float],
    checks: dict[str, bool | None],
    output_formats: set[str],
    stage_count: int,
    asset_count: int,
    artifact_zip_sha256: str,
    artifact_zip_bytes: int,
    reference_asset_count: int,
    source_plan_sha256: str,
    renderer_manifest_sha256: str,
    location: str,
    errors: list[str],
) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{location} 的 evidence manifest 无法读取：{exc}。")
        return
    if not isinstance(payload, dict):
        errors.append(f"{location} 的 evidence manifest 必须是 JSON 对象。")
        return
    if payload.get("schema_version") != 2:
        errors.append(f"{location} 的 evidence manifest 必须使用 schema_version=2。")
    if payload.get("case_id") != case_id or payload.get("run_id") != run_id:
        errors.append(f"{location} 的 evidence manifest 与结果行不匹配。")
    if payload.get("measurement_scope") != case["measurement_scope"]:
        errors.append(f"{location} 的 evidence manifest 计时边界与案例表不一致。")
    if payload.get("evidence_status") != case["evidence_status"]:
        errors.append(f"{location} 的 evidence manifest 证据状态与案例表不一致。")
    manifest_timings = payload.get("timings_seconds")
    manifest_elapsed = (
        manifest_timings.get("machine_end_to_end_seconds")
        if isinstance(manifest_timings, dict)
        else None
    )
    if not isinstance(manifest_elapsed, (int, float)) or abs(float(manifest_elapsed) - elapsed) > 1e-6:
        errors.append(f"{location} 的 evidence manifest 与结果行机器耗时不一致。")
    if not isinstance(manifest_timings, dict):
        errors.append(f"{location} 的 evidence manifest 缺少分阶段耗时。")
    else:
        for field, value in timings.items():
            manifest_value = manifest_timings.get(field)
            if not isinstance(manifest_value, (int, float)) or abs(float(manifest_value) - value) > 1e-6:
                errors.append(f"{location} 的 evidence manifest.{field} 与结果行不一致。")
    if payload.get("semantic_review_status") != "not_measured":
        errors.append(f"{location} 的 evidence manifest 必须标记语义评审未测量。")

    manifest_checks = payload.get("checks")
    if not isinstance(manifest_checks, dict):
        errors.append(f"{location} 的 evidence manifest 缺少分项检查。")
    else:
        for field, value in checks.items():
            if manifest_checks.get(field) is not value:
                errors.append(f"{location} 的 evidence manifest.{field} 与结果行不一致。")

    input_plan = payload.get("input_plan")
    if not isinstance(input_plan, dict):
        errors.append(f"{location} 的 evidence manifest 缺少输入计划绑定。")
    elif (
        input_plan.get("path") != case["plan_path"]
        or input_plan.get("sha256") != case["plan_sha256"]
        or input_plan.get("sha256") != source_plan_sha256
    ):
        errors.append(f"{location} 的 evidence manifest 未绑定当前案例 FigurePlan SHA-256。")

    expected_profile = {
        "layout_family": case["layout_family"],
        "layout_preset": case["layout_preset"],
        "theme": case["theme"],
    }
    if payload.get("render_profile") != expected_profile:
        errors.append(f"{location} 的 evidence manifest 渲染配置与当前案例不一致。")
    references = payload.get("reference_assets")
    if not isinstance(references, list) or len(references) != reference_asset_count:
        errors.append(f"{location} 的 evidence manifest 参考来源数量与结果行不一致。")
    plan_payload = case.get("plan_payload")
    current_stages = plan_payload.get("stages", []) if isinstance(plan_payload, dict) else []
    current_references = plan_payload.get("reference_assets", []) if isinstance(plan_payload, dict) else []
    if references != current_references:
        errors.append(f"{location} 的 evidence manifest 参考来源与当前 FigurePlan 不一致。")
    if not isinstance(current_stages, list) or stage_count != len(current_stages):
        errors.append(f"{location} 的 stage_count 与当前 FigurePlan 不一致。")
    expected_asset_files = {
        f"{stage.get('asset_key')}.png"
        for stage in current_stages
        if isinstance(stage, dict) and isinstance(stage.get("asset_key"), str)
    }
    manifest_formats = payload.get("output_formats")
    if (
        not isinstance(manifest_formats, list)
        or not all(isinstance(value, str) for value in manifest_formats)
        or set(manifest_formats) != output_formats
    ):
        errors.append(f"{location} 的 evidence manifest 输出格式与结果行不一致。")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append(f"{location} 的 evidence manifest 缺少带哈希的产物清单。")
        return
    artifact_map: dict[str, dict[str, Any]] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            errors.append(f"{location} 的产物清单含非对象条目。")
            continue
        artifact_path = item.get("path")
        artifact_sha = item.get("sha256")
        artifact_bytes = item.get("bytes")
        if not isinstance(artifact_path, str):
            errors.append(f"{location} 的产物路径无效。")
            continue
        pure_path = PurePosixPath(artifact_path)
        if pure_path.is_absolute() or ".." in pure_path.parts or artifact_path in artifact_map:
            errors.append(f"{location} 的产物路径越界或重复：{artifact_path!r}。")
            continue
        if not isinstance(artifact_bytes, int) or artifact_bytes < 0:
            errors.append(f"{location} 的产物大小无效：{artifact_path!r}。")
        if not isinstance(artifact_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_sha):
            errors.append(f"{location} 的产物哈希无效：{artifact_path!r}。")
        artifact_map[artifact_path] = item

    plan_artifact = artifact_map.get("figure_plan.json")
    if not isinstance(plan_artifact, dict) or plan_artifact.get("sha256") != case["plan_sha256"]:
        errors.append(f"{location} 的已打包 FigurePlan 哈希与当前输入不一致。")

    renderer = payload.get("renderer_manifest")
    renderer_content: dict[str, Any] | None = None
    renderer_path = ""
    if not isinstance(renderer, dict) or not isinstance(renderer.get("content"), dict):
        errors.append(f"{location} 的 evidence manifest 缺少渲染 manifest 快照。")
    else:
        renderer_content = renderer["content"]
        renderer_path = str(renderer.get("path", ""))
        renderer_artifact = artifact_map.get(renderer_path)
        embedded_sha = _json_payload_sha256(renderer_content)
        if (
            renderer.get("sha256") != renderer_manifest_sha256
            or renderer.get("sha256") != embedded_sha
            or not isinstance(renderer_artifact, dict)
            or renderer_artifact.get("sha256") != embedded_sha
        ):
            errors.append(f"{location} 的渲染 manifest 快照、哈希与产物清单不一致。")
        if renderer_content.get("plan_sha256") != case["plan_sha256"]:
            errors.append(f"{location} 的渲染 manifest 未绑定当前 FigurePlan SHA-256。")
        if renderer_content.get("schema_version") != 2 or renderer_content.get("plan") != "figure_plan.json":
            errors.append(f"{location} 的渲染 manifest 版本或计划文件名无效。")
        if renderer_content.get("evidence_status") != case["evidence_status"]:
            errors.append(f"{location} 的渲染 manifest 证据状态与当前计划不一致。")
        if renderer_content.get("reference_assets") != current_references:
            errors.append(f"{location} 的渲染 manifest 参考来源与当前计划不一致。")
        if any(renderer_content.get(key) != value for key, value in expected_profile.items()):
            errors.append(f"{location} 的渲染 manifest 配置与当前计划不一致。")

        layout_qa = renderer_content.get("layout_qa")
        layout_ok = layout_qa.get("ok") if isinstance(layout_qa, dict) else None
        if not isinstance(layout_ok, bool) or layout_ok is not checks.get("renderer_layout_qa_pass"):
            errors.append(f"{location} 的 renderer_layout_qa_pass 与渲染 manifest.layout_qa.ok 不一致。")

        theme_token = renderer_content.get("theme_tokens")
        theme_sha = renderer_content.get("theme_tokens_sha256")
        if not isinstance(theme_token, str) or Path(theme_token).name != theme_token:
            errors.append(f"{location} 的渲染 manifest 主题 token 路径不安全。")
        else:
            theme_path = ROOT / "skill" / "design-research-figures" / "assets" / "themes" / theme_token
            if not theme_path.is_file() or theme_sha != _sha256(theme_path):
                errors.append(f"{location} 的渲染 manifest 主题 token 哈希与当前仓库不一致。")
            else:
                try:
                    theme_payload = json.loads(theme_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    errors.append(f"{location} 的当前主题 token 无法读取。")
                else:
                    if not isinstance(theme_payload, dict) or theme_payload.get("id") != case["theme"]:
                        errors.append(f"{location} 的主题 token ID 与当前案例不一致。")

        renderer_parent = PurePosixPath(renderer_path).parent
        declared_outputs = renderer_content.get("outputs")
        output_hashes = renderer_content.get("output_sha256")
        if not isinstance(declared_outputs, dict) or not isinstance(output_hashes, dict):
            errors.append(f"{location} 的渲染 manifest 缺少输出哈希。")
        else:
            for output_key in ("svg", "pdf", "png"):
                output_name = declared_outputs.get(output_key)
                output_record = artifact_map.get((renderer_parent / str(output_name)).as_posix())
                if (
                    not isinstance(output_name, str)
                    or not isinstance(output_record, dict)
                    or output_hashes.get(output_name) != output_record.get("sha256")
                ):
                    errors.append(f"{location} 的渲染 manifest {output_key.upper()} 哈希与产物清单不一致。")

        declared_assets = renderer_content.get("assets")
        if not isinstance(declared_assets, list) or len(declared_assets) != asset_count:
            errors.append(f"{location} 的渲染 manifest 素材数量与结果行不一致。")
        else:
            declared_asset_files = {
                str(asset.get("file")) for asset in declared_assets if isinstance(asset, dict)
            }
            if declared_asset_files != expected_asset_files:
                errors.append(f"{location} 的渲染 manifest 素材键与当前 FigurePlan 不一致。")
            for asset in declared_assets:
                if not isinstance(asset, dict):
                    errors.append(f"{location} 的渲染 manifest 素材条目无效。")
                    continue
                asset_record = artifact_map.get(f"assets/processed/{asset.get('file', '')}")
                if not isinstance(asset_record, dict) or asset_record.get("sha256") != asset.get("sha256"):
                    errors.append(f"{location} 的渲染 manifest 素材哈希与产物清单不一致。")

    asset_sources = payload.get("asset_sources")
    if not isinstance(asset_sources, list) or len(asset_sources) != asset_count or asset_count != stage_count:
        errors.append(f"{location} 的素材证据数量与 stage_count/asset_count 不一致。")
    else:
        source_keys = {
            str(source.get("key")) for source in asset_sources if isinstance(source, dict)
        }
        if {f"{key}.png" for key in source_keys} != expected_asset_files:
            errors.append(f"{location} 的素材证据键与当前 FigurePlan 不一致。")
        for source in asset_sources:
            if not isinstance(source, dict):
                errors.append(f"{location} 的素材证据条目无效。")
                continue
            for prefix in ("raw", "processed", "manifest"):
                source_path = source.get(f"{prefix}_path")
                source_sha = source.get(f"{prefix}_sha256")
                artifact = artifact_map.get(str(source_path))
                if not isinstance(artifact, dict) or artifact.get("sha256") != source_sha:
                    errors.append(f"{location} 的素材 {prefix} 哈希与产物清单不一致。")

    delivery_qa = payload.get("delivery_qa")
    if not isinstance(delivery_qa, dict):
        errors.append(f"{location} 的 evidence manifest 缺少组合交付 QA 证据。")
    else:
        layout_ok = delivery_qa.get("renderer_layout_qa_ok")
        audit_ok = delivery_qa.get("output_audit_ok")
        combined_ok = delivery_qa.get("combined_ok")
        if layout_ok is not checks.get("renderer_layout_qa_pass"):
            errors.append(f"{location} 的交付 QA 布局结果与结果行不一致。")
        if audit_ok is not checks.get("output_audit_pass"):
            errors.append(f"{location} 的交付 QA 输出审计结果与结果行不一致。")
        expected_combined = layout_ok is True and audit_ok is True
        if combined_ok is not expected_combined or combined_ok is not checks.get("delivery_qa_pass"):
            errors.append(f"{location} 的 delivery_qa_pass 不是 layout_qa.ok 与输出审计的逻辑与。")
        audit_report = delivery_qa.get("output_audit_report")
        qa_artifact = artifact_map.get("qa/qa_report.json")
        if (
            not isinstance(audit_report, dict)
            or audit_report.get("ok") is not audit_ok
            or not isinstance(qa_artifact, dict)
            or _json_payload_sha256(audit_report) != qa_artifact.get("sha256")
        ):
            errors.append(f"{location} 的输出 QA 快照、结果与产物哈希不一致。")

    zip_records = [item for item in artifact_map.values() if str(item.get("path", "")).endswith(".zip")]
    if len(zip_records) != 1:
        errors.append(f"{location} 的 evidence manifest 必须包含一个 ZIP 哈希记录。")
    else:
        zip_record = zip_records[0]
        if zip_record.get("sha256") != artifact_zip_sha256 or zip_record.get("bytes") != artifact_zip_bytes:
            errors.append(f"{location} 的 evidence manifest 与结果行 ZIP 哈希或大小不一致。")


def _human_template_status() -> dict[str, int]:
    _, rows = _read_csv(HUMAN_TEMPLATE)
    counts = Counter(row.get("measurement_status", "") for row in rows)
    return {"planned": counts.get("planned", 0), "measured": counts.get("measured", 0)}


def analyze(results_path: Path, cases_path: Path = DEFAULT_CASES) -> dict[str, Any]:
    cases = _load_cases(cases_path)
    header, rows = _read_csv(results_path)
    missing = [column for column in RESULT_COLUMNS if column not in header]
    errors = [f"机器结果表缺少列：{', '.join(missing)}"] if missing else []
    parsed: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    seen_case_ids: set[str] = set()

    for row in rows:
        location = f"机器结果表第 {row['_row_number']} 行"
        case_id = row.get("case_id", "")
        run_id = row.get("run_id", "")
        if row.get("measurement_status") != "measured":
            errors.append(f"{location} 不是 measured 实测行。")
        if case_id not in cases:
            errors.append(f"{location} 引用了未知 case_id={case_id!r}。")
            continue
        case = cases[case_id]
        if run_id in seen_run_ids or not run_id:
            errors.append(f"{location} 的 run_id 为空或重复：{run_id!r}。")
        seen_run_ids.add(run_id)
        if case_id in seen_case_ids:
            errors.append(f"{location} 的 case_id={case_id} 有多条行；当前报告要求每案例一次实测。")
        seen_case_ids.add(case_id)

        started_at = _parse_timestamp(row.get("started_at", ""), "started_at", location, errors)
        ended_at = _parse_timestamp(row.get("ended_at", ""), "ended_at", location, errors)
        if started_at and ended_at and ended_at < started_at:
            errors.append(f"{location} 的 ended_at 早于 started_at。")
        if row.get("measurement_scope") != case["measurement_scope"]:
            errors.append(f"{location} 的 measurement_scope 与案例表不一致。")

        timings: dict[str, float] = {}
        for field in TIMING_FIELDS:
            parsed_time = _parse_float(row.get(field, ""), field, location, errors, positive=False)
            if parsed_time is not None:
                timings[field] = parsed_time
        elapsed = _parse_float(
            row.get("machine_end_to_end_seconds", ""),
            "machine_end_to_end_seconds",
            location,
            errors,
            positive=True,
        )
        if elapsed is None:
            continue
        if len(timings) == len(TIMING_FIELDS) and sum(timings.values()) > elapsed + 0.05:
            errors.append(f"{location} 的阶段耗时之和超过机器端到端耗时。")
        stage_count = _parse_int(row.get("stage_count", ""), "stage_count", location, errors)
        asset_count = _parse_int(row.get("asset_count", ""), "asset_count", location, errors)
        reference_asset_count = _parse_int(
            row.get("reference_asset_count", ""),
            "reference_asset_count",
            location,
            errors,
            positive=False,
        )
        if stage_count is not None and asset_count is not None and stage_count != asset_count:
            errors.append(f"{location} 的 stage_count 与 asset_count 不一致。")

        checks = {
            field: _parse_bool(row.get(field, ""), field, location, errors)
            for field in (*CHECK_FIELDS, "machine_run_success")
        }
        combined_delivery_qa = (
            checks.get("renderer_layout_qa_pass") is True
            and checks.get("output_audit_pass") is True
        )
        if (
            checks.get("delivery_qa_pass") is not None
            and checks["delivery_qa_pass"] is not combined_delivery_qa
        ):
            errors.append(f"{location} 的 delivery_qa_pass 不是布局 QA 与输出审计的逻辑与。")
        expected_success = all(checks.get(field) is True for field in CHECK_FIELDS)
        if checks.get("machine_run_success") is not None and checks["machine_run_success"] != expected_success:
            errors.append(f"{location} 的 machine_run_success 与分项检查不一致。")
        if row.get("semantic_review_status") != "not_measured":
            errors.append(f"{location} 必须把 semantic_review_status 标为 not_measured。")

        formats = {value for value in row.get("output_formats", "").split("|") if value}
        required_formats = set(case["required_output_formats"].split("|"))
        if checks.get("required_formats_present") and not required_formats.issubset(formats):
            errors.append(f"{location} 声称格式完整，但 output_formats 缺少必需格式。")
        manifest_path = _resolve_evidence_path(row.get("evidence_manifest_path", ""), errors, location)
        source_plan_sha256 = row.get("source_plan_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", source_plan_sha256):
            errors.append(f"{location} 的 source_plan_sha256 不是 64 位小写十六进制哈希。")
        elif source_plan_sha256 != case["plan_sha256"]:
            errors.append(f"{location} 的 source_plan_sha256 与当前案例 FigurePlan 不一致。")
        renderer_manifest_sha256 = row.get("renderer_manifest_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", renderer_manifest_sha256):
            errors.append(f"{location} 的 renderer_manifest_sha256 不是 64 位小写十六进制哈希。")
        artifact_zip_sha256 = row.get("artifact_zip_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_zip_sha256):
            errors.append(f"{location} 的 artifact_zip_sha256 不是 64 位小写十六进制哈希。")
        artifact_zip_bytes = _parse_int(
            row.get("artifact_zip_bytes", ""), "artifact_zip_bytes", location, errors
        )
        retention = row.get("artifact_retention", "")
        if retention not in {"committed", "not_committed_size_control"}:
            errors.append(f"{location} 的 artifact_retention 口径无效。")
        artifact_zip_path_value = row.get("artifact_zip_path", "")
        zip_path: Path | None = None
        if retention == "committed":
            zip_path = _resolve_evidence_path(artifact_zip_path_value, errors, location)
            if zip_path is not None:
                if not zipfile.is_zipfile(zip_path):
                    errors.append(f"{location} 的 artifact_zip_path 不是有效 ZIP。")
                elif artifact_zip_bytes is not None and zip_path.stat().st_size != artifact_zip_bytes:
                    errors.append(f"{location} 的 ZIP 大小与结果行不一致。")
                elif hashlib.sha256(zip_path.read_bytes()).hexdigest() != artifact_zip_sha256:
                    errors.append(f"{location} 的 ZIP 哈希与结果行不一致。")
        elif artifact_zip_path_value:
            errors.append(f"{location} 的未提交大体积 ZIP 不应保留仓库路径。")
        if manifest_path is not None:
            _validate_manifest(
                manifest_path,
                case=case,
                case_id=case_id,
                run_id=run_id,
                elapsed=elapsed,
                timings=timings,
                checks=checks,
                output_formats=formats,
                stage_count=stage_count or 0,
                asset_count=asset_count or 0,
                artifact_zip_sha256=artifact_zip_sha256,
                artifact_zip_bytes=artifact_zip_bytes or 0,
                reference_asset_count=reference_asset_count or 0,
                source_plan_sha256=source_plan_sha256,
                renderer_manifest_sha256=renderer_manifest_sha256,
                location=location,
                errors=errors,
            )

        baseline = float(case["baseline_seconds"])
        parsed.append(
            {
                "case_id": case_id,
                "case_title": case["case_title"],
                "scenario": case["scenario"],
                "complexity_class": case["complexity_class"],
                "render_profile": {
                    "layout_family": case["layout_family"],
                    "layout_preset": case["layout_preset"],
                    "theme": case["theme"],
                },
                "baseline": {
                    "kind": "personal_self_reported_historical_lower_bound",
                    "seconds": baseline,
                    "display": "≥1小时" if baseline == 3600 else "≥8小时（1个工作日下界）",
                    "source": case["baseline_source"],
                    "scope": case["baseline_scope"],
                    "same_task_human_timing": False,
                },
                "machine_measurement": {
                    "run_id": run_id,
                    "seconds": elapsed,
                    "runtime_environment": row.get("runtime_environment"),
                    "scope": row.get("measurement_scope"),
                    "delivery_qa_pass": checks.get("delivery_qa_pass") is True,
                    "renderer_layout_qa_pass": checks.get("renderer_layout_qa_pass") is True,
                    "output_audit_pass": checks.get("output_audit_pass") is True,
                    "source_plan_sha256": source_plan_sha256,
                    "renderer_manifest_sha256": renderer_manifest_sha256,
                    "machine_run_success": checks.get("machine_run_success") is True,
                    "semantic_review_status": "not_measured",
                    "reference_asset_count": reference_asset_count,
                    "output_formats": sorted(formats),
                    "evidence_manifest_path": row.get("evidence_manifest_path"),
                    "artifact_zip_path": row.get("artifact_zip_path"),
                    "artifact_zip_sha256": artifact_zip_sha256,
                    "artifact_zip_bytes": artifact_zip_bytes,
                    "artifact_retention": retention,
                    "timings_seconds": timings,
                },
                "relative_lower_bound_multiple": round(baseline / elapsed, 1),
                "comparison_label": COMPARISON_LABEL,
            }
        )

    missing_cases = sorted(set(cases).difference(seen_case_ids))
    if missing_cases:
        errors.append(f"机器结果表缺少案例：{', '.join(missing_cases)}。")
    if errors:
        raise ValidationProblem(errors)

    machine_seconds = [item["machine_measurement"]["seconds"] for item in parsed]
    ratios = [item["relative_lower_bound_multiple"] for item in parsed]
    successful = sum(item["machine_measurement"]["machine_run_success"] for item in parsed)
    qa_passed = sum(item["machine_measurement"]["delivery_qa_pass"] for item in parsed)
    return {
        "status": "ok" if successful == len(parsed) else "measured_with_failures",
        "generated_from": {
            "case_definitions": cases_path.relative_to(ROOT).as_posix(),
            "machine_results": results_path.relative_to(ROOT).as_posix(),
        },
        "measurement_scope": {
            "included": "已写入 FigurePlan → 通用fallback生成或本地语义素材读取/抠图 → SVG/PDF/PNG渲染 → 自动交付QA → ZIP关闭",
            "excluded": [
                "自然语言规划",
                "人工计划编写",
                "参考图在线搜索",
                "局部语义素材首次生成",
                "人工语义评审",
                "上传",
                "PPT编辑",
            ],
            "single_run_per_case": True,
        },
        "summary": {
            "representative_cases": len(parsed),
            "measured_machine_runs": len(parsed),
            "successful_machine_runs": successful,
            "delivery_qa_passes": qa_passed,
            "presentation_spacious_cases": sum(
                item["render_profile"]["layout_preset"] == "presentation-spacious" for item in parsed
            ),
            "gpu_green_tech_cases": sum(
                item["render_profile"]["theme"] == "gpu-green-tech" for item in parsed
            ),
            "reference_linked_cases": sum(
                (item["machine_measurement"]["reference_asset_count"] or 0) > 0 for item in parsed
            ),
            "reference_assets_total": sum(
                item["machine_measurement"]["reference_asset_count"] or 0 for item in parsed
            ),
            "machine_end_to_end_seconds": {
                "min": round(min(machine_seconds), 3),
                "median": round(statistics.median(machine_seconds), 3),
                "max": round(max(machine_seconds), 3),
            },
            "relative_lower_bound_multiple": {
                "min": min(ratios),
                "max": max(ratios),
                "label": COMPARISON_LABEL,
            },
        },
        "human_comparison_benchmark": {
            **_human_template_status(),
            "source": "benchmark/results_template.csv",
            "interpretation": "人工对照尚未实测，不得据此声称团队人效或人工节省。",
        },
        "case_runs": parsed,
        "claim_boundary": {
            "required_note": BOUNDARY_NOTE,
            "allowed": [
                "陈述每个案例的单次机器链路墙钟时间、自动交付QA结果和输出格式。",
                f"把 {COMPARISON_LABEL} 作为两个不同来源时间数字的尺度商，并保留“≥”和边界说明。",
            ],
            "not_supported": [
                "团队人效提升",
                "同题人工对照提速",
                "节省工时",
                "语义准确率提升",
                "人工对照显著性",
            ],
        },
    }


def _evidence_link(value: str) -> str:
    prefix = "benchmark/"
    return value[len(prefix) :] if value.startswith(prefix) else value


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# FigureFlow 代表案例机器链路实测",
        "",
        f"> **口径边界：** {report['claim_boundary']['required_note']}",
        "",
        "## 本次测量",
        "",
        f"- 代表案例：{summary['representative_cases']} 个；机器实测：{summary['measured_machine_runs']} 次（每案例单次）。",
        f"- 链路成功：{summary['successful_machine_runs']}/{summary['measured_machine_runs']}；自动交付 QA 通过：{summary['delivery_qa_passes']}/{summary['measured_machine_runs']}。",
        f"- 新版视觉链路覆盖：`presentation-spacious` {summary['presentation_spacious_cases']} 个案例；`gpu-green-tech` {summary['gpu_green_tech_cases']} 个案例。",
        f"- 来源可追溯案例：{summary['reference_linked_cases']} 个，共 {summary['reference_assets_total']} 条 Commons 参考元数据；渲染阶段不联网抓取。",
        "- 计时范围：已写入 FigurePlan 到交付 ZIP 关闭；不含自然语言规划、人工计划编写、参考图在线搜索、局部语义素材首次生成、人工语义评审、上传和 PPT 编辑。",
        "- 自动 QA 须同时通过渲染 manifest 的布局检查与 PNG/PDF 输出审计；语义质量未测量。",
        "- 原始运行目录与大体积 ZIP 留在临时目录；仓库只保留脱敏 CSV、摘要和带哈希的小型 manifest。",
        "",
        "| 代表任务 | 视觉配置 | 个人自报历史下界（非同题） | 机器 E2E 单次实测 | 时间尺度倍率* | 自动交付 QA | 输出 | 证据 |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for item in report["case_runs"]:
        machine = item["machine_measurement"]
        manifest = _evidence_link(machine["evidence_manifest_path"])
        qa = "通过" if machine["delivery_qa_pass"] else "未通过"
        formats = "/".join(value.upper() for value in machine["output_formats"])
        profile = item["render_profile"]
        lines.append(
            f"| {item['case_id']} {item['case_title']} | {profile['theme']} + {profile['layout_preset']} | "
            f"{item['baseline']['display']} | "
            f"{machine['seconds']:.3f} 秒 | ≥{item['relative_lower_bound_multiple']:.1f}× | "
            f"{qa} | {formats} | [manifest]({manifest}) |"
        )
    human = report["human_comparison_benchmark"]
    lines.extend(
        [
            "",
            f"\\*“时间尺度倍率” = 个人自报历史下界 ÷ 机器链路实测，不是同题 speedup。个人下界来源于本次答辩准备对话；机器数字来自各行链接的带哈希 manifest。",
            "",
            "## 机器时间汇总",
            "",
            f"- 最短 / 中位 / 最长：{summary['machine_end_to_end_seconds']['min']:.3f} / {summary['machine_end_to_end_seconds']['median']:.3f} / {summary['machine_end_to_end_seconds']['max']:.3f} 秒。",
            f"- {COMPARISON_LABEL}范围：≥{summary['relative_lower_bound_multiple']['min']:.1f}×–≥{summary['relative_lower_bound_multiple']['max']:.1f}×。",
            "",
            "## 尚未获得的证据",
            "",
            f"- 人工对照矩阵仍为 {human['planned']} planned / {human['measured']} measured（来源：`{human['source']}`）。",
            "- 因此不能陈述团队人效提升、同题人工对照提速、节省工时、语义准确率提升或统计显著性。",
            "",
        ]
    )
    return "\n".join(lines)


def _resolve_cli_path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="?", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    results = _resolve_cli_path(args.results)
    cases = _resolve_cli_path(args.cases)
    json_out = _resolve_cli_path(args.json_out)
    markdown_out = _resolve_cli_path(args.markdown_out)
    try:
        report = analyze(results, cases)
    except ValidationProblem as exc:
        for error in exc.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    json_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_out.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
