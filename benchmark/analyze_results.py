#!/usr/bin/env python3
"""Validate and summarize FigureFlow benchmark measurements.

The script deliberately does not impute missing values or ship example performance
numbers. Only rows explicitly marked ``measured`` contribute to the report.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


METHODS = ("manual_docs", "whole_image_edit", "figureflow")
BASELINES = ("manual_docs", "whole_image_edit")
STATUSES = ("planned", "measured", "excluded")

REQUIRED_COLUMNS = (
    "assignment_id",
    "run_id",
    "participant_id",
    "reviewer_id",
    "task_id",
    "method",
    "trial_index",
    "method_order",
    "measurement_status",
    "exclusion_reason",
    "started_at",
    "ended_at",
    "time_limit_seconds",
    "total_elapsed_seconds",
    "first_pass_seconds",
    "active_work_seconds",
    "local_edit_seconds",
    "pipeline_runtime_seconds",
    "semantic_items_total",
    "semantic_items_correct",
    "text_formula_errors",
    "layout_defects",
    "non_target_items_total",
    "non_target_items_unchanged",
    "interaction_rounds",
    "editable_delivery",
    "acceptance_pass",
    "reviewer_blinded",
    "evidence_uri",
    "notes",
)

PERFORMANCE_COLUMNS = (
    "started_at",
    "ended_at",
    "time_limit_seconds",
    "total_elapsed_seconds",
    "first_pass_seconds",
    "active_work_seconds",
    "local_edit_seconds",
    "pipeline_runtime_seconds",
    "semantic_items_total",
    "semantic_items_correct",
    "text_formula_errors",
    "layout_defects",
    "non_target_items_total",
    "non_target_items_unchanged",
    "interaction_rounds",
    "editable_delivery",
    "acceptance_pass",
    "reviewer_blinded",
    "evidence_uri",
)

TIME_METRICS = (
    "total_elapsed_seconds",
    "first_pass_seconds",
    "active_work_seconds",
    "local_edit_seconds",
)


class ValidationProblem(Exception):
    """Raised when one or more CSV validation errors are found."""

    def __init__(self, errors: Sequence[str]):
        super().__init__("\n".join(errors))
        self.errors = list(errors)


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


def _load_task_assignments(path: Path) -> dict[str, tuple[str, str]]:
    header, rows = _read_csv(path)
    needed = {"assignment_id", "task_id", "method"}
    missing = sorted(needed.difference(header))
    errors = [f"任务表缺少列：{', '.join(missing)}"] if missing else []
    assignments: dict[str, tuple[str, str]] = {}
    combinations: set[tuple[str, str]] = set()
    tasks_to_methods: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        location = f"{path}:{row['_row_number']}"
        assignment_id = row.get("assignment_id", "")
        task_id = row.get("task_id", "")
        method = row.get("method", "")
        if not assignment_id or not task_id or not method:
            errors.append(f"{location} 的 assignment_id、task_id 和 method 均不能为空。")
            continue
        if method not in METHODS:
            errors.append(f"{location} 的 method={method!r} 不在允许列表中。")
        if assignment_id in assignments:
            errors.append(f"{location} 的 assignment_id={assignment_id!r} 重复。")
        combination = (task_id, method)
        if combination in combinations:
            errors.append(f"{location} 的 task_id + method 组合重复：{combination}。")
        assignments[assignment_id] = combination
        combinations.add(combination)
        tasks_to_methods[task_id].add(method)
    for task_id, methods in sorted(tasks_to_methods.items()):
        missing_methods = sorted(set(METHODS).difference(methods))
        if missing_methods:
            errors.append(f"任务 {task_id} 缺少方法条件：{', '.join(missing_methods)}。")
    if errors:
        raise ValidationProblem(errors)
    return assignments


def _parse_float(
    row: dict[str, str],
    field: str,
    errors: list[str],
    *,
    required: bool = False,
    positive: bool = False,
) -> float | None:
    value = row.get(field, "")
    location = f"结果表第 {row['_row_number']} 行"
    if not value:
        if required:
            errors.append(f"{location} 的 {field} 不能为空。")
        return None
    try:
        number = float(value)
    except ValueError:
        errors.append(f"{location} 的 {field} 必须是数字，当前为 {value!r}。")
        return None
    if not math.isfinite(number):
        errors.append(f"{location} 的 {field} 必须是有限数字。")
        return None
    if positive and number <= 0:
        errors.append(f"{location} 的 {field} 必须大于 0。")
    elif not positive and number < 0:
        errors.append(f"{location} 的 {field} 不能小于 0。")
    return number


def _parse_int(
    row: dict[str, str],
    field: str,
    errors: list[str],
    *,
    required: bool = False,
    positive: bool = False,
) -> int | None:
    number = _parse_float(row, field, errors, required=required, positive=positive)
    if number is None:
        return None
    if not number.is_integer():
        errors.append(f"结果表第 {row['_row_number']} 行的 {field} 必须是整数。")
        return None
    return int(number)


def _parse_bool(
    row: dict[str, str], field: str, errors: list[str], *, required: bool = False
) -> bool | None:
    value = row.get(field, "").lower()
    if not value:
        if required:
            errors.append(f"结果表第 {row['_row_number']} 行的 {field} 不能为空。")
        return None
    if value not in {"true", "false"}:
        errors.append(
            f"结果表第 {row['_row_number']} 行的 {field} 只能填写 true 或 false，当前为 {value!r}。"
        )
        return None
    return value == "true"


def _parse_timestamp(row: dict[str, str], field: str, errors: list[str]) -> datetime | None:
    value = row.get(field, "")
    if not value:
        errors.append(f"结果表第 {row['_row_number']} 行的 {field} 不能为空。")
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        errors.append(f"结果表第 {row['_row_number']} 行的 {field} 不是有效 ISO 8601 时间。")
        return None
    if timestamp.tzinfo is None:
        errors.append(f"结果表第 {row['_row_number']} 行的 {field} 必须包含时区。")
        return None
    return timestamp


def _validate_results(
    results_path: Path, task_assignments: dict[str, tuple[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    header, rows = _read_csv(results_path)
    missing = [field for field in REQUIRED_COLUMNS if field not in header]
    errors: list[str] = []
    if missing:
        errors.append(f"结果表缺少列：{', '.join(missing)}")

    measured: list[dict[str, Any]] = []
    status_counts = {status: 0 for status in STATUSES}
    seen_run_ids: set[str] = set()
    seen_trials: set[tuple[str, str, int, str]] = set()
    seen_orders: dict[tuple[str, str, int], set[int]] = defaultdict(set)

    for row in rows:
        line = row["_row_number"]
        status = row.get("measurement_status", "").lower()
        if status not in STATUSES:
            errors.append(
                f"结果表第 {line} 行的 measurement_status 必须是 {', '.join(STATUSES)} 之一。"
            )
            continue
        status_counts[status] += 1

        assignment_id = row.get("assignment_id", "")
        task_id = row.get("task_id", "")
        method = row.get("method", "")
        if not assignment_id or not task_id or not method:
            errors.append(f"结果表第 {line} 行的 assignment_id、task_id 和 method 均不能为空。")
        elif assignment_id not in task_assignments:
            errors.append(f"结果表第 {line} 行引用了未知 assignment_id={assignment_id!r}。")
        elif task_assignments[assignment_id] != (task_id, method):
            errors.append(
                f"结果表第 {line} 行的 assignment_id 与 task_id/method 不匹配。"
            )
        if method and method not in METHODS:
            errors.append(f"结果表第 {line} 行的 method={method!r} 不在允许列表中。")

        if status == "planned":
            present = [field for field in PERFORMANCE_COLUMNS if row.get(field, "")]
            if present:
                errors.append(
                    f"结果表第 {line} 行仍标记为 planned，但已有实测字段：{', '.join(present)}。"
                )
            continue
        if status == "excluded":
            if not row.get("exclusion_reason", ""):
                errors.append(f"结果表第 {line} 行标记为 excluded 时必须填写 exclusion_reason。")
            continue

        required_text = ("run_id", "participant_id", "reviewer_id", "evidence_uri")
        for field in required_text:
            if not row.get(field, ""):
                errors.append(f"结果表第 {line} 行的 {field} 不能为空。")
        run_id = row.get("run_id", "")
        if run_id:
            if run_id in seen_run_ids:
                errors.append(f"结果表第 {line} 行的 run_id={run_id!r} 重复。")
            seen_run_ids.add(run_id)

        trial_index = _parse_int(row, "trial_index", errors, required=True, positive=True)
        method_order = _parse_int(row, "method_order", errors, required=True, positive=True)
        if method_order is not None and method_order not in {1, 2, 3}:
            errors.append(f"结果表第 {line} 行的 method_order 必须是 1、2 或 3。")

        started_at = _parse_timestamp(row, "started_at", errors)
        ended_at = _parse_timestamp(row, "ended_at", errors)
        if started_at is not None and ended_at is not None and ended_at <= started_at:
            errors.append(f"结果表第 {line} 行的 ended_at 必须晚于 started_at。")

        numbers: dict[str, float | int | None] = {}
        numbers["time_limit_seconds"] = _parse_float(
            row, "time_limit_seconds", errors, required=True, positive=True
        )
        numbers["total_elapsed_seconds"] = _parse_float(
            row, "total_elapsed_seconds", errors, required=True, positive=True
        )
        numbers["first_pass_seconds"] = _parse_float(
            row, "first_pass_seconds", errors, positive=True
        )
        numbers["active_work_seconds"] = _parse_float(
            row, "active_work_seconds", errors, required=True
        )
        numbers["local_edit_seconds"] = _parse_float(row, "local_edit_seconds", errors)
        numbers["pipeline_runtime_seconds"] = _parse_float(
            row, "pipeline_runtime_seconds", errors
        )
        numbers["semantic_items_total"] = _parse_int(
            row, "semantic_items_total", errors, required=True, positive=True
        )
        numbers["semantic_items_correct"] = _parse_int(
            row, "semantic_items_correct", errors, required=True
        )
        numbers["text_formula_errors"] = _parse_int(
            row, "text_formula_errors", errors, required=True
        )
        numbers["layout_defects"] = _parse_int(row, "layout_defects", errors, required=True)
        numbers["non_target_items_total"] = _parse_int(
            row, "non_target_items_total", errors, positive=True
        )
        numbers["non_target_items_unchanged"] = _parse_int(
            row, "non_target_items_unchanged", errors
        )
        numbers["interaction_rounds"] = _parse_int(
            row, "interaction_rounds", errors, required=True
        )

        editable_delivery = _parse_bool(row, "editable_delivery", errors, required=True)
        acceptance_pass = _parse_bool(row, "acceptance_pass", errors, required=True)
        reviewer_blinded = _parse_bool(row, "reviewer_blinded", errors, required=True)

        elapsed = numbers["total_elapsed_seconds"]
        active = numbers["active_work_seconds"]
        first_pass = numbers["first_pass_seconds"]
        local_edit = numbers["local_edit_seconds"]
        time_limit = numbers["time_limit_seconds"]
        if elapsed is not None and active is not None and active > elapsed:
            errors.append(f"结果表第 {line} 行的 active_work_seconds 不能大于 total_elapsed_seconds。")
        if elapsed is not None and local_edit is not None and local_edit > elapsed:
            errors.append(f"结果表第 {line} 行的 local_edit_seconds 不能大于 total_elapsed_seconds。")
        if acceptance_pass is True:
            if first_pass is None:
                errors.append(f"结果表第 {line} 行验收通过时必须填写 first_pass_seconds。")
            elif elapsed is not None and first_pass > elapsed:
                errors.append(f"结果表第 {line} 行的 first_pass_seconds 不能大于 total_elapsed_seconds。")
            elif time_limit is not None and first_pass > time_limit:
                errors.append(f"结果表第 {line} 行的 first_pass_seconds 超过 time_limit_seconds。")
        elif acceptance_pass is False and first_pass is not None:
            errors.append(f"结果表第 {line} 行验收失败时 first_pass_seconds 必须留空。")

        semantic_total = numbers["semantic_items_total"]
        semantic_correct = numbers["semantic_items_correct"]
        if (
            semantic_total is not None
            and semantic_correct is not None
            and semantic_correct > semantic_total
        ):
            errors.append(
                f"结果表第 {line} 行的 semantic_items_correct 不能大于 semantic_items_total。"
            )

        non_target_total = numbers["non_target_items_total"]
        non_target_unchanged = numbers["non_target_items_unchanged"]
        if (non_target_total is None) != (non_target_unchanged is None):
            errors.append(
                f"结果表第 {line} 行的 non_target_items_total 与 non_target_items_unchanged 必须同时填写或同时留空。"
            )
        elif (
            non_target_total is not None
            and non_target_unchanged is not None
            and non_target_unchanged > non_target_total
        ):
            errors.append(
                f"结果表第 {line} 行的 non_target_items_unchanged 不能大于 non_target_items_total。"
            )
        if method != "figureflow" and numbers["pipeline_runtime_seconds"] is not None:
            errors.append(
                f"结果表第 {line} 行只有 figureflow 方法可填写 pipeline_runtime_seconds。"
            )

        if trial_index is not None and row.get("participant_id", "") and task_id and method:
            trial_key = (row["participant_id"], task_id, trial_index, method)
            if trial_key in seen_trials:
                errors.append(
                    f"结果表第 {line} 行重复了 participant_id + task_id + trial_index + method。"
                )
            seen_trials.add(trial_key)
            if method_order is not None:
                order_key = (row["participant_id"], task_id, trial_index)
                if method_order in seen_orders[order_key]:
                    errors.append(
                        f"结果表第 {line} 行在同一参与者、任务和轮次中重复使用 method_order={method_order}。"
                    )
                seen_orders[order_key].add(method_order)

        prepared: dict[str, Any] = dict(row)
        prepared.update(numbers)
        prepared["trial_index"] = trial_index
        prepared["method_order"] = method_order
        prepared["editable_delivery"] = editable_delivery
        prepared["acceptance_pass"] = acceptance_pass
        prepared["reviewer_blinded"] = reviewer_blinded
        if semantic_total and semantic_correct is not None:
            prepared["semantic_accuracy"] = semantic_correct / semantic_total
        else:
            prepared["semantic_accuracy"] = None
        if non_target_total and non_target_unchanged is not None:
            prepared["non_target_stability"] = non_target_unchanged / non_target_total
        else:
            prepared["non_target_stability"] = None
        measured.append(prepared)

    if errors:
        raise ValidationProblem(errors)
    return measured, status_counts


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    """Return the type-7 sample quantile used by common analysis tools."""

    index = (len(sorted_values) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[lower]
    fraction = index - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _clean_number(value: float) -> int | float:
    rounded = round(value, 6)
    return int(rounded) if float(rounded).is_integer() else rounded


def describe(values: Iterable[float | int | None]) -> dict[str, int | float | None]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return {"n": 0, "median": None, "q1": None, "q3": None, "iqr": None}
    median = _quantile(clean, 0.5)
    if len(clean) < 2:
        q1 = q3 = iqr = None
    else:
        q1 = _quantile(clean, 0.25)
        q3 = _quantile(clean, 0.75)
        iqr = q3 - q1
    return {
        "n": len(clean),
        "median": _clean_number(median),
        "q1": _clean_number(q1) if q1 is not None else None,
        "q3": _clean_number(q3) if q3 is not None else None,
        "iqr": _clean_number(iqr) if iqr is not None else None,
    }


def _boolean_outcome(rows: Sequence[dict[str, Any]], field: str) -> dict[str, int | float]:
    values = [row[field] for row in rows if row.get(field) is not None]
    successes = sum(value is True for value in values)
    total = len(values)
    return {
        "n": total,
        "successes": successes,
        "failures": total - successes,
        "success_rate": round(successes / total, 6) if total else 0.0,
    }


def _summarize_method(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        field: describe(row.get(field) for row in rows)
        for field in (
            "total_elapsed_seconds",
            "first_pass_seconds",
            "active_work_seconds",
            "local_edit_seconds",
            "pipeline_runtime_seconds",
            "interaction_rounds",
            "semantic_accuracy",
            "non_target_stability",
        )
    }
    errors: dict[str, Any] = {}
    for field in ("text_formula_errors", "layout_defects"):
        values = [row[field] for row in rows if row.get(field) is not None]
        errors[field] = {"total": int(sum(values)), **describe(values)}
    return {
        "n_measured": len(rows),
        "metrics": metrics,
        "outcomes": {
            "acceptance_pass": _boolean_outcome(rows, "acceptance_pass"),
            "editable_delivery": _boolean_outcome(rows, "editable_delivery"),
        },
        "error_counts": errors,
    }


def _pair_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return (row["participant_id"], row["task_id"], row["trial_index"])


def _compare_baseline(rows: Sequence[dict[str, Any]], baseline: str) -> dict[str, Any]:
    figureflow = {_pair_key(row): row for row in rows if row["method"] == "figureflow"}
    baseline_rows = {_pair_key(row): row for row in rows if row["method"] == baseline}
    matching_keys = sorted(set(figureflow).intersection(baseline_rows))
    comparison: dict[str, Any] = {
        "baseline": baseline,
        "pair_key": ["participant_id", "task_id", "trial_index"],
        "matched_runs": len(matching_keys),
        "ratio_definition": "baseline_time / figureflow_time; values > 1 mean FigureFlow was faster",
        "ratios": {},
    }
    if not matching_keys:
        comparison["status"] = "no_paired_data"
        return comparison

    unavailable: list[str] = []
    for metric in TIME_METRICS:
        ratios: list[float] = []
        for key in matching_keys:
            baseline_value = baseline_rows[key].get(metric)
            figureflow_value = figureflow[key].get(metric)
            if (
                baseline_value is not None
                and figureflow_value is not None
                and baseline_value > 0
                and figureflow_value > 0
            ):
                ratios.append(baseline_value / figureflow_value)
        if ratios:
            comparison["ratios"][metric] = describe(ratios)
        else:
            unavailable.append(metric)

    paired_outcomes = {"figureflow_wins": 0, "ties": 0, "baseline_wins": 0}
    for key in matching_keys:
        ff_pass = int(bool(figureflow[key]["acceptance_pass"]))
        baseline_pass = int(bool(baseline_rows[key]["acceptance_pass"]))
        if ff_pass > baseline_pass:
            paired_outcomes["figureflow_wins"] += 1
        elif ff_pass < baseline_pass:
            paired_outcomes["baseline_wins"] += 1
        else:
            paired_outcomes["ties"] += 1
    comparison["paired_acceptance"] = paired_outcomes
    comparison["unavailable_ratio_metrics"] = unavailable
    comparison["status"] = "ok" if comparison["ratios"] else "paired_but_no_positive_time_values"
    return comparison


def _display_path(path: Path) -> str:
    """Keep reports portable and avoid leaking a workstation's absolute path."""

    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path.name


def analyze(results_path: Path, tasks_path: Path) -> dict[str, Any]:
    assignments = _load_task_assignments(tasks_path)
    measured, status_counts = _validate_results(results_path, assignments)
    if not measured:
        return {
            "schema_version": "1.0",
            "status": "no_measured_data",
            "source": {"results": _display_path(results_path), "tasks": _display_path(tasks_path)},
            "data_counts": {**status_counts, "total_rows": sum(status_counts.values())},
            "method_summaries": {},
            "comparisons": [],
            "message": "没有 measurement_status=measured 的行；未计算统计量或方法比值。",
        }

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in measured:
        grouped[row["method"]].append(row)
    summaries = {
        method: _summarize_method(grouped[method]) for method in METHODS if grouped.get(method)
    }
    comparisons = [_compare_baseline(measured, baseline) for baseline in BASELINES]
    return {
        "schema_version": "1.0",
        "status": "ok",
        "source": {"results": _display_path(results_path), "tasks": _display_path(tasks_path)},
        "data_counts": {**status_counts, "total_rows": sum(status_counts.values())},
        "method_summaries": summaries,
        "comparisons": comparisons,
        "notes": [
            "所有统计仅使用 measurement_status=measured 的实测行。",
            "四分位数采用线性插值；少于两条观测时 q1、q3 和 iqr 为 null。",
            "耗时比值使用严格配对，不使用未配对组中位数构造比值。",
        ],
    }


def _format_stat(stat: dict[str, Any]) -> str:
    if not stat or stat.get("n", 0) == 0:
        return "—"
    median = stat["median"]
    iqr = stat.get("iqr")
    return f"{median}（IQR {iqr}）" if iqr is not None else f"{median}（IQR 未定义）"


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# FigureFlow 基准测试分析", ""]
    if report["status"] == "no_measured_data":
        lines.extend(
            [
                "当前没有实测行，因此未生成效率、成功率或方法比值结论。",
                "",
                f"- 计划行：{report['data_counts']['planned']}",
                f"- 排除行：{report['data_counts']['excluded']}",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "所有结果仅来自标记为 `measured` 的记录。时间单位均为秒。",
            "",
            "| 方法 | 实测数 | 验收成功率 | 首个合格版本中位数 | 主动操作中位数 | 本地修改中位数 | 文字/公式错误总数 | 版式缺陷总数 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for method, summary in report["method_summaries"].items():
        outcomes = summary["outcomes"]["acceptance_pass"]
        rate = f"{outcomes['success_rate'] * 100:.1f}% ({outcomes['successes']}/{outcomes['n']})"
        metrics = summary["metrics"]
        errors = summary["error_counts"]
        lines.append(
            "| "
            + " | ".join(
                [
                    method,
                    str(summary["n_measured"]),
                    rate,
                    _format_stat(metrics["first_pass_seconds"]),
                    _format_stat(metrics["active_work_seconds"]),
                    _format_stat(metrics["local_edit_seconds"]),
                    str(errors["text_formula_errors"]["total"]),
                    str(errors["layout_defects"]["total"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## 严格配对比较", ""])
    for comparison in report["comparisons"]:
        baseline = comparison["baseline"]
        if comparison["status"] == "no_paired_data":
            lines.append(f"- `{baseline}`：没有同参与者、同任务、同轮次的配对数据，未计算比值。")
            continue
        lines.append(f"- `{baseline}`：匹配 {comparison['matched_runs']} 组。")
        if not comparison["ratios"]:
            lines.append("  - 没有双方都大于零的配对耗时，未计算比值。")
        for metric, stat in comparison["ratios"].items():
            lines.append(
                f"  - `{metric}` 的基线/FigureFlow 中位比值：{_format_stat(stat)}，n={stat['n']}。"
            )
    lines.extend(
        [
            "",
            "> 比值定义为“基线耗时 / FigureFlow 耗时”；大于 1 表示该配对中 FigureFlow 更快。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="校验 FigureFlow 实测 CSV，并输出不含虚构值的汇总。"
    )
    parser.add_argument("results_csv", type=Path, help="从 results_template.csv 复制并填写的结果表")
    parser.add_argument(
        "--tasks",
        type=Path,
        default=Path(__file__).with_name("tasks.csv"),
        help="任务矩阵，默认使用脚本同目录的 tasks.csv",
    )
    parser.add_argument("--json-out", type=Path, help="可选：写入 JSON 报告")
    parser.add_argument("--markdown-out", type=Path, help="可选：写入 Markdown 摘要")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = analyze(args.results_csv, args.tasks)
    except ValidationProblem as problem:
        print("数据校验失败：", file=sys.stderr)
        for error in problem.errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        _write_text(args.json_out, json_text)
    if args.markdown_out:
        _write_text(args.markdown_out, render_markdown(report))
    print(json_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
