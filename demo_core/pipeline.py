"""End-to-end FigureFlow orchestration with measurable stage timings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal, Sequence

from .asset_pipeline import create_contact_sheet, prepare_assets, public_asset_records
from .planner import DEFAULT_MODEL, plan_figure
from .reference_import import materialize_reference_assets, public_reference_import_records
from .renderer_adapter import audit_outputs, render_plan
from .schemas import FigurePlan, LayoutPreset, ReferenceAsset, ThemeName, display_units


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path(os.getenv("FIGUREFLOW_OUTPUT_DIR", ROOT / "demo" / "output")).expanduser()
LAYOUTS = ("ribbon", "bowtie", "dual-rail")
RUN_DIR_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
SPACIOUS_BODY_LINE_UNITS = 24
MAX_PLAN_WARNINGS = 6


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: str
    plan: dict[str, object]
    planning: dict[str, object]
    selected_layout: str
    candidates: list[tuple[str, str]]
    raw_preview: str
    processed_preview: str
    contact_sheet: str
    final_png: str
    final_svg: str
    final_pdf: str
    bundle_zip: str
    manifest: str
    metrics: dict[str, int]
    qa: dict[str, object]
    notice: str
    reference_previews: tuple[str, ...] = ()
    reference_imports: tuple[dict[str, object], ...] = ()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, base: Path) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()


def _prune_outputs() -> None:
    """Bound disk use by deleting only old FigureFlow-owned run artifacts."""
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        keep = max(1, min(100, int(os.getenv("FIGUREFLOW_MAX_RUNS", "8"))))
    except ValueError:
        keep = 8
    run_dirs = sorted(
        (path for path in OUTPUT_ROOT.iterdir() if path.is_dir() and RUN_DIR_PATTERN.fullmatch(path.name)),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in run_dirs[max(0, keep - 1) :]:
        if stale.parent.resolve() == OUTPUT_ROOT.resolve() and RUN_DIR_PATTERN.fullmatch(stale.name):
            shutil.rmtree(stale)
        delivery = OUTPUT_ROOT / f"{stale.name}-figureflow-delivery.zip"
        if delivery.is_file():
            delivery.unlink()

    deliveries = sorted(
        OUTPUT_ROOT.glob("*-figureflow-delivery.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in deliveries[max(0, keep - 1) :]:
        stem = stale.name.removesuffix("-figureflow-delivery.zip")
        if RUN_DIR_PATTERN.fullmatch(stem) and stale.parent.resolve() == OUTPUT_ROOT.resolve():
            stale.unlink()


def _truncate_display_text(value: str, max_units: int) -> str:
    """Keep a readable prefix within a renderer display-unit budget."""
    if display_units(value) <= max_units:
        return value
    ellipsis = "…"
    content_budget = max_units - display_units(ellipsis)
    if content_budget <= 0:
        return ellipsis if display_units(ellipsis) <= max_units else ""
    kept: list[str] = []
    used = 0
    for char in value:
        units = display_units(char)
        if used + units > content_budget:
            break
        kept.append(char)
        used += units
    return "".join(kept).rstrip() + ellipsis


def _compact_spacious_body(title: str, body: Sequence[str]) -> tuple[list[str], str | None]:
    """Convert a valid three-line body into two lines without silent information loss.

    The first semantic line remains intact. The remaining two lines are merged when
    they fit. If they do not, both retain a visible prefix and their exact source
    text is returned as an audit warning for the plan/manifest.
    """
    lines = list(body)
    if len(lines) <= 2:
        return lines, None

    first, second, third = lines
    separator = "；"
    combined = f"{second}{separator}{third}"
    if display_units(combined) <= SPACIOUS_BODY_LINE_UNITS:
        return [first, combined], None

    available = SPACIOUS_BODY_LINE_UNITS - display_units(separator)
    second_units = display_units(second)
    third_units = display_units(third)
    second_budget = min(second_units, available // 2)
    third_budget = min(third_units, available - second_budget)
    remaining = available - second_budget - third_budget
    if remaining:
        add_second = min(remaining, second_units - second_budget)
        second_budget += add_second
        remaining -= add_second
        third_budget += min(remaining, third_units - third_budget)

    compacted = (
        f"{_truncate_display_text(second, second_budget)}"
        f"{separator}{_truncate_display_text(third, third_budget)}"
    )
    warning = f"投屏压缩原文[{title}]：{second}｜{third}"
    if len(warning) > 80:
        raise ValueError(f"cannot safely preserve spacious body source text for stage {title!r}")
    return [first, compacted], warning


def _apply_plan_overrides(
    plan: FigurePlan,
    *,
    layout_override: Literal["ribbon", "bowtie", "dual-rail"] | None,
    layout_preset_override: LayoutPreset | None,
    theme_override: ThemeName | None,
) -> FigurePlan:
    """Apply UI overrides while adapting renderer-constrained presentation copy."""
    payload = plan.model_dump()
    if layout_override:
        payload["layout_family"] = layout_override
    if theme_override:
        payload["theme"] = theme_override
    if layout_preset_override:
        payload["layout_preset"] = layout_preset_override

    if payload["layout_preset"] == "presentation-spacious":
        compaction_warnings: list[str] = []
        for stage in payload["stages"]:
            compacted, warning = _compact_spacious_body(stage["title"], stage["body"])
            stage["body"] = compacted
            if warning:
                compaction_warnings.append(warning)
        existing_warnings = list(payload["warnings"])
        if len(compaction_warnings) + len(existing_warnings) > MAX_PLAN_WARNINGS:
            raise ValueError(
                "presentation-spacious override needs more warning slots to preserve truncated source text"
            )
        # Surface copy compression before pre-existing warnings; the exact source
        # remains in FigurePlan and bundled figure_plan.json even when cards are terse.
        payload["warnings"] = compaction_warnings + existing_warnings

    return FigurePlan.model_validate(payload)


def run_pipeline(
    brief: str,
    *,
    mode: Literal["auto", "online", "offline"] = "auto",
    layout_override: Literal["ribbon", "bowtie", "dual-rail"] | None = None,
    layout_preset_override: LayoutPreset | None = None,
    theme_override: ThemeName | None = None,
    live_icon: bool = False,
    model: str = DEFAULT_MODEL,
    reference_assets: Sequence[ReferenceAsset] = (),
    reference_import_ids: Sequence[str] = (),
    reference_visual_id: str | None = None,
) -> RunResult:
    started_total = perf_counter()
    _prune_outputs()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    plan_started = perf_counter()
    plan, planning = plan_figure(brief, mode=mode, model=model, reference_assets=reference_assets)
    if planning.mode == "online" and planning.identity_status not in {"reported_match", "reported_snapshot"}:
        raise RuntimeError("Online delivery requires a service-reported Sol model identity")
    planning_ms = round((perf_counter() - plan_started) * 1000)
    plan = _apply_plan_overrides(
        plan,
        layout_override=layout_override,
        layout_preset_override=layout_preset_override,
        theme_override=theme_override,
    )
    if reference_visual_id:
        plan_payload = plan.model_dump()
        for asset in plan_payload["reference_assets"]:
            asset["used_in_layout"] = asset["id"] == reference_visual_id
        plan = FigurePlan.model_validate(plan_payload)
    plan_path = run_dir / "figure_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

    selected_reference_ids = list(dict.fromkeys(reference_import_ids))
    if reference_visual_id and reference_visual_id not in selected_reference_ids:
        selected_reference_ids.append(reference_visual_id)
    reference_started = perf_counter()
    imported_references = materialize_reference_assets(
        plan.reference_assets,
        run_dir,
        selected_ids=selected_reference_ids,
    )
    reference_import_ms = round((perf_counter() - reference_started) * 1000)
    imported_by_id = {item.id: item for item in imported_references}
    asset_overrides: dict[str, Path] = {}
    asset_override_reference_ids: dict[str, str] = {}
    if reference_visual_id:
        try:
            visual_reference = imported_by_id[reference_visual_id]
        except KeyError as exc:
            raise ValueError("reference_visual_id must identify an imported reference") from exc
        first_stage_key = plan.stages[0].asset_key
        asset_overrides[first_stage_key] = Path(visual_reference.source_path)
        asset_override_reference_ids[first_stage_key] = visual_reference.id

    asset_started = perf_counter()
    use_live_icon = live_icon and planning.mode == "online"
    assets, live_metadata = prepare_assets(
        plan.stages,
        run_dir,
        live_icon=use_live_icon,
        model=model,
        expected_reported_model=planning.reported_model,
        asset_overrides=asset_overrides,
        asset_override_reference_ids=asset_override_reference_ids,
    )
    asset_ms = round((perf_counter() - asset_started) * 1000)
    generation_ms = sum(asset.generation_ms for asset in assets)
    cutout_ms = sum(asset.cutout_ms for asset in assets)
    contact_sheet = create_contact_sheet(assets, run_dir / "assets" / "asset_pipeline.png")

    render_started = perf_counter()
    candidates: list[tuple[str, str]] = []
    candidate_outputs: dict[str, dict[str, str]] = {}
    for family in LAYOUTS:
        candidate_plan = plan.model_copy(update={"layout_family": family})
        candidate_plan_path = run_dir / "candidates" / family / "plan.json"
        candidate_plan_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_plan_path.write_text(candidate_plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        outputs = render_plan(
            candidate_plan_path,
            run_dir / "assets" / "processed",
            candidate_plan_path.parent,
            f"figureflow_{family.replace('-', '_')}",
        )
        candidate_outputs[family] = outputs
        candidates.append((outputs["png"], family))
    render_ms = round((perf_counter() - render_started) * 1000)
    selected_layout = plan.layout_family
    selected = candidate_outputs[selected_layout]

    qa_started = perf_counter()
    qa_by_layout: dict[str, dict[str, object]] = {}
    for family, outputs in candidate_outputs.items():
        report = audit_outputs(
            Path(outputs["png"]),
            Path(outputs["pdf"]),
            run_dir / "qa" / family,
        )
        renderer_manifest = json.loads(Path(outputs["manifest"]).read_text(encoding="utf-8"))
        layout_qa = renderer_manifest.get("layout_qa", {})
        report["layout_qa"] = layout_qa
        report["ok"] = bool(report.get("ok")) and bool(layout_qa.get("ok"))
        qa_by_layout[family] = report
    qa_ms = round((perf_counter() - qa_started) * 1000)
    qa = {
        "ok": all(report.get("ok") for report in qa_by_layout.values()),
        "selected_layout": selected_layout,
        "reference_assets": [asset.model_dump() for asset in plan.reference_assets],
        "reference_imports": public_reference_import_records(imported_references, run_dir),
        "selected": qa_by_layout[selected_layout],
        "by_layout": qa_by_layout,
    }

    for family, outputs in candidate_outputs.items():
        if family == selected_layout:
            continue
        for key in ("svg", "pdf", "manifest"):
            Path(outputs[key]).unlink(missing_ok=True)

    metrics = {
        "planning_ms": planning_ms,
        "reference_import_ms": reference_import_ms,
        "icon_generation_ms": generation_ms,
        "cutout_ms": cutout_ms,
        "asset_pipeline_ms": asset_ms,
        "render_3_layouts_ms": render_ms,
        "qa_ms": qa_ms,
    }

    selected_paths = {key: Path(value) for key, value in selected.items()}
    reference_artifacts = [
        path
        for imported in imported_references
        for path in (Path(imported.source_path), Path(imported.manifest_path))
    ]
    artifacts = [plan_path, contact_sheet, *reference_artifacts, *selected_paths.values()]
    reference_import_records = public_reference_import_records(imported_references, run_dir)
    manifest_data: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence_status": plan.evidence_status,
        "notice": "演示素材与耗时仅代表本次运行；未完成团队范围对照实验。",
        "planning": planning.model_dump(),
        "selected_layout": selected_layout,
        "metrics_ms": metrics,
        "assets": public_asset_records(assets, run_dir),
        "reference_imports": reference_import_records,
        "reference_visual_id": reference_visual_id,
        "live_icon": live_metadata,
        "qa": qa,
        "artifacts": {
            _relative(path, run_dir): _sha256(path)
            for path in artifacts
            if path.is_file()
        },
    }
    manifest_path = run_dir / "run_manifest.json"
    bundle_zip = OUTPUT_ROOT / f"{run_id}-figureflow-delivery.zip"
    packaging_started = perf_counter()
    with zipfile.ZipFile(bundle_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and path != manifest_path:
                archive.write(path, path.relative_to(run_dir).as_posix())
        metrics["packaging_ms"] = round((perf_counter() - packaging_started) * 1000)
        metrics["total_ms"] = round((perf_counter() - started_total) * 1000)
        manifest_data["metrics_ms"] = metrics
        manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        archive.write(manifest_path, manifest_path.name)

    if planning.mode == "online":
        mode_notice = f"在线规划：{planning.model}"
    elif planning.fallback_reason and planning.fallback_reason.startswith("online planning failed"):
        mode_notice = "在线尝试失败，最终使用固定离线预设；未换用其他模型"
    else:
        mode_notice = "固定离线预设复演；当前输入未参与语义规划，也未调用 GPT-5.6-sol"
    live_notice = " · 实时生成 1 个 Icon" if live_metadata else (" · 未执行实时 Icon" if live_icon else "")
    if imported_references:
        reference_notice = f" · 已安全导入 {len(imported_references)} 张参考图"
        if reference_visual_id:
            reference_notice += "，所选参考图已进入排版"
    else:
        reference_notice = ""
    qa_notice = "QA 通过" if qa.get("ok") else "QA 未通过，请查看交付包中的报告"
    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        plan=plan.model_dump(),
        planning=planning.model_dump(),
        selected_layout=selected_layout,
        candidates=candidates,
        raw_preview=assets[0].raw_path,
        processed_preview=assets[0].processed_path,
        contact_sheet=str(contact_sheet),
        final_png=selected["png"],
        final_svg=selected["svg"],
        final_pdf=selected["pdf"],
        bundle_zip=str(bundle_zip),
        manifest=str(manifest_path),
        metrics=metrics,
        qa=qa,
        notice=f"{mode_notice}{live_notice}{reference_notice} · {qa_notice}",
        reference_previews=tuple(item.source_path for item in imported_references),
        reference_imports=tuple(dict(item) for item in reference_import_records),
    )
