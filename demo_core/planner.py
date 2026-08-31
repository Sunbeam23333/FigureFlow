"""OpenAI Responses API planner with an explicit offline replay mode."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Sequence

from openai import OpenAI

from .schemas import FigurePlan, PlanningMetadata, ReferenceAsset


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRESET = ROOT / "presets" / "tencent_figureflow_demo.json"
DEFAULT_PROMPT = ROOT / "prompts" / "figure_planner.md"
DEFAULT_MODEL = "gpt-5.6-sol"


class PlanningError(RuntimeError):
    """A user-actionable planning failure."""


def load_preset(path: Path = DEFAULT_PRESET) -> FigurePlan:
    return FigurePlan.model_validate_json(path.read_text(encoding="utf-8"))


def _attach_references(plan: FigurePlan, assets: Sequence[ReferenceAsset]) -> FigurePlan:
    """Attach only caller/provider-validated references, never model-invented URLs."""
    payload = plan.model_dump()
    payload["reference_assets"] = [ReferenceAsset.model_validate(asset).model_dump() for asset in assets]
    return FigurePlan.model_validate(payload)


def _usage_value(response: object, field: str) -> int | None:
    usage = getattr(response, "usage", None)
    value = getattr(usage, field, None) if usage is not None else None
    return int(value) if value is not None else None


def _online_plan(brief: str, model: str) -> tuple[FigurePlan, PlanningMetadata]:
    instructions = DEFAULT_PROMPT.read_text(encoding="utf-8")
    client = OpenAI(timeout=90.0, max_retries=2)
    response = client.responses.parse(
        model=model,
        reasoning={"effort": "medium"},
        instructions=instructions,
        input=brief,
        text_format=FigurePlan,
        store=False,
        max_output_tokens=3200,
    )
    plan = response.output_parsed
    if plan is None:
        raise PlanningError("GPT-5.6-sol did not return a valid FigurePlan.")
    metadata = PlanningMetadata(
        mode="online",
        requested_mode="online",
        model=model,
        response_id=getattr(response, "id", None),
        input_tokens=_usage_value(response, "input_tokens"),
        output_tokens=_usage_value(response, "output_tokens"),
    )
    return plan, metadata


def plan_figure(
    brief: str,
    *,
    mode: Literal["auto", "online", "offline"] = "auto",
    model: str | None = None,
    reference_assets: Sequence[ReferenceAsset] = (),
) -> tuple[FigurePlan, PlanningMetadata]:
    """Plan a figure without ever silently substituting the requested online model."""

    brief = brief.strip()
    if not brief:
        raise PlanningError("Please provide a workflow or figure brief.")
    if len(brief) > 8_000:
        raise PlanningError("The brief is too long for this demo (8,000 character limit).")

    target_model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    has_key = bool(os.getenv("OPENAI_API_KEY"))

    if mode == "offline" or (mode == "auto" and not has_key):
        reason = "offline mode selected" if mode == "offline" else "OPENAI_API_KEY is not set"
        metadata = PlanningMetadata(
            mode="offline",
            requested_mode=mode,
            model=None,
            fallback_reason=reason,
        )
        return _attach_references(load_preset(), reference_assets), metadata

    if mode == "online" and not has_key:
        raise PlanningError(
            "Online mode requires OPENAI_API_KEY in the server environment; the key is never entered in the browser."
        )

    try:
        plan, metadata = _online_plan(brief, target_model)
        metadata.requested_mode = mode
        return _attach_references(plan, reference_assets), metadata
    except Exception as exc:  # the UI maps this to a concise, non-secret message
        if mode == "online":
            raise PlanningError(
                f"在线规划失败（MODEL_REQUEST_FAILED，目标模型：{target_model}）。请检查服务端 API 配置。"
            ) from exc
        metadata = PlanningMetadata(
            mode="offline",
            requested_mode=mode,
            model=target_model,
            fallback_reason=f"online planning failed: {type(exc).__name__}",
        )
        preset = load_preset()
        preset.warnings.append("在线规划失败，本次展示离线预设；未替换为其他模型。")
        return _attach_references(preset, reference_assets), metadata
