"""Conservative Gradio adapter for the opt-in research-figure harness."""

from __future__ import annotations

import os
from pathlib import Path
import re
import uuid
from typing import Callable, Sequence

import gradio as gr
from gradio.processing_utils import get_upload_folder


SOURCE_SUFFIXES = {".pdf", ".md", ".txt", ".tex"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
MAX_SOURCES = 8
MAX_IMAGES = 8
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 100 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 50 * 1024 * 1024
RESEARCH_MAX_CALLS = 24
RESEARCH_MAX_SECONDS = 1200


class ResearchUIError(ValueError):
    """A safe, user-facing research-entry validation error."""


def research_enabled(*, public_demo: bool | None = None) -> bool:
    public = (
        os.getenv("FIGUREFLOW_PUBLIC_DEMO", "false").lower() == "true"
        if public_demo is None
        else public_demo
    )
    opted_in = os.getenv("FIGUREFLOW_ENABLE_RESEARCH", "false").lower() == "true"
    share = os.getenv("GRADIO_SHARE", "false").lower() == "true"
    server = os.getenv("GRADIO_SERVER_NAME", "127.0.0.1").strip().lower()
    loopback = server in {"127.0.0.1", "localhost", "::1"}
    authenticated = bool(
        os.getenv("FIGUREFLOW_BASIC_AUTH_USER") and os.getenv("FIGUREFLOW_BASIC_AUTH_PASSWORD")
    )
    return opted_in and not public and not share and (loopback or authenticated)


def _uploaded_paths(
    values: Sequence[str | Path] | str | Path | None,
    *,
    suffixes: set[str],
    maximum_count: int,
    maximum_bytes: int,
    maximum_total_bytes: int,
    upload_root: str | Path | None = None,
) -> list[Path]:
    if values is None:
        return []
    entries = [values] if isinstance(values, (str, Path)) else list(values)
    if len(entries) > maximum_count:
        raise ResearchUIError(f"最多上传 {maximum_count} 个文件")
    root = Path(upload_root or get_upload_folder()).resolve()
    result: list[Path] = []
    total = 0
    for value in entries:
        path = Path(str(value)).resolve(strict=True)
        if path != root and root not in path.parents:
            raise ResearchUIError("仅接受本次通过页面上传的文件")
        if not path.is_file() or path.suffix.lower() not in suffixes:
            raise ResearchUIError("上传文件的类型不受支持")
        size = path.stat().st_size
        if size <= 0 or size > maximum_bytes:
            raise ResearchUIError("上传文件为空或超过单文件大小限制")
        total += size
        result.append(path)
    if total > maximum_total_bytes:
        raise ResearchUIError("上传文件总大小超过限制")
    return result


def run_research(
    source_uploads,
    asset_uploads,
    style_uploads,
    brief: str,
    confirmed: bool,
    *,
    output_root: str | Path,
    public_demo: bool | None = None,
    enabled: bool | None = None,
    upload_root: str | Path | None = None,
    harness_factory: Callable | None = None,
    client_factory: Callable | None = None,
):
    allowed = research_enabled(public_demo=public_demo) if enabled is None else enabled
    if not allowed:
        return (
            "### 研究入口未开放\n\n该功能仅供显式启用的本地或已认证部署。",
            [],
            None,
            [],
            {},
        )
    if not confirmed:
        return "### 未开始\n\n请先确认上传的文件和图片将发送给模型。", [], None, [], {}
    brief = (brief or "").strip()
    if not brief or len(brief) > 12_000:
        return "### 输入无效\n\n请提供 1–12,000 字符的主图需求。", [], None, [], {}
    try:
        sources = _uploaded_paths(
            source_uploads,
            suffixes=SOURCE_SUFFIXES,
            maximum_count=MAX_SOURCES,
            maximum_bytes=MAX_SOURCE_BYTES,
            maximum_total_bytes=MAX_TOTAL_SOURCE_BYTES,
            upload_root=upload_root,
        )
        assets = _uploaded_paths(
            asset_uploads,
            suffixes=IMAGE_SUFFIXES,
            maximum_count=MAX_IMAGES,
            maximum_bytes=MAX_IMAGE_BYTES,
            maximum_total_bytes=MAX_TOTAL_IMAGE_BYTES,
            upload_root=upload_root,
        )
        styles = _uploaded_paths(
            style_uploads,
            suffixes=IMAGE_SUFFIXES,
            maximum_count=MAX_IMAGES,
            maximum_bytes=MAX_IMAGE_BYTES,
            maximum_total_bytes=MAX_TOTAL_IMAGE_BYTES,
            upload_root=upload_root,
        )
        if not sources:
            raise ResearchUIError("请至少上传一个 PDF/Markdown/TXT/TeX 证据文件")
        if len(assets) + len(styles) > MAX_IMAGES:
            raise ResearchUIError("素材图与风格图合计最多 8 张")
    except (OSError, ResearchUIError) as exc:
        message = str(exc) if isinstance(exc, ResearchUIError) else "无法读取已上传的文件，请重新上传。"
        return f"### 上传校验失败\n\n{message}", [], None, [], {}

    if harness_factory is None:
        from .research_harness import ResearchHarness

        harness_factory = ResearchHarness
    if client_factory is None:
        from openai import OpenAI

        client_factory = lambda: OpenAI(timeout=300, max_retries=0)

    run_root = Path(output_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    run_dir = run_root / f"research-{uuid.uuid4().hex}"
    asset_records = [
        {"id": f"upload_{index:02d}", "path": str(path), "kind": "user-supplied asset; establish evidence status from source",
         "meaning": path.name}
        for index, path in enumerate(assets, 1)
    ]
    try:
        harness = harness_factory(
            client=client_factory(),
            sources=sources,
            brief=brief,
            run_dir=run_dir,
            assets=asset_records,
            style_images=styles,
            max_calls=RESEARCH_MAX_CALLS,
            max_seconds=RESEARCH_MAX_SECONDS,
            reasoning_effort="medium",
            require_exploration=True,
        )
        result = harness.run()
    except Exception as exc:
        return (
            f"### 研究运行未完成\n\n未生成可交付结果。错误类型：`{type(exc).__name__}`",
            [],
            None,
            [],
            {"status": "draft_only", "stop_reason": type(exc).__name__},
        )

    previews = []
    for candidate_id, record in harness.candidates.items():
        png = Path(record["stem"]).with_suffix(".png")
        if png.is_file():
            previews.append((str(png), candidate_id))
    passed = result.get("status") == "automated_review_passed"
    final_png = str(run_dir / "final.png") if passed and (run_dir / "final.png").is_file() else None
    downloads = []
    if passed:
        downloads = [
            str(path)
            for path in (run_dir / "final.svg", run_dir / "final.pdf", run_dir / "delivery.zip")
            if path.is_file()
        ]
    heading = "自动评审通过（人工批准待定）" if passed else "仅保留候选草稿"
    status = (
        f"### {heading}\n\n状态：`{result.get('status', 'draft_only')}` · "
        f"预算：{RESEARCH_MAX_CALLS} calls / {RESEARCH_MAX_SECONDS} s · 不会自动发布"
    )
    return status, previews, final_png, downloads, result


def build_research_section(*, output_root: str | Path, public_demo: bool) -> None:
    available = research_enabled(public_demo=public_demo)
    with gr.Accordion("论文主图（实验）", open=False):
        gr.Markdown(
            "上方是 **3–6 节点受约束流程图模式**。本区是独立的论文主图实验："
            "读取显式上传的证据，生成多个可编辑 scene，并进行单独的自动视觉评审"
            "与修订。默认预算为 24 次模型调用 / 1200 秒；不会自动发布，自动通过也"
            "不等于人工批准。"
        )
        if not available:
            gr.Markdown(
                "**当前未开放。** 需在非公开演示环境设置 "
                "`FIGUREFLOW_ENABLE_RESEARCH=true`；非回环地址部署还必须配置"
                "基本认证，且不允许 Gradio share。"
            )
        sources = gr.File(
            label="证据文件（PDF / Markdown / TXT / TeX，最多 8 个）",
            file_count="multiple",
            file_types=[".pdf", ".md", ".txt", ".tex"],
            type="filepath",
            interactive=available,
        )
        with gr.Row():
            assets = gr.File(
                label="可选论文素材（PNG / JPG）",
                file_count="multiple",
                file_types=[".png", ".jpg", ".jpeg"],
                type="filepath",
                interactive=available,
            )
            styles = gr.File(
                label="可选风格参考（PNG / JPG）",
                file_count="multiple",
                file_types=[".png", ".jpg", ".jpeg"],
                type="filepath",
                interactive=available,
            )
        brief = gr.Textbox(label="主图需求", lines=5, max_lines=10, interactive=available)
        confirm = gr.Checkbox(
            label="我确认：上传的文件、素材图和风格图将发送给模型处理",
            value=False,
            interactive=available,
        )
        run = gr.Button("运行论文主图实验", variant="primary", interactive=available)
        status = gr.Markdown("尚未运行。")
        candidates = gr.Gallery(label="候选预览（草稿也会保留）", columns=3, object_fit="contain")
        final = gr.Image(
            label="最终预览（仅自动评审通过时显示）",
            type="filepath",
            buttons=["fullscreen"],
        )
        downloads = gr.File(label="最终交付（仅自动评审通过时显示）", file_count="multiple")
        details = gr.JSON(label="研究运行状态")
        run.click(
            lambda source_uploads, asset_uploads, style_uploads, request, acknowledged: run_research(
                source_uploads,
                asset_uploads,
                style_uploads,
                request,
                acknowledged,
                output_root=output_root,
                public_demo=public_demo,
            ),
            inputs=[sources, assets, styles, brief, confirm],
            outputs=[status, candidates, final, downloads, details],
            api_name=False,
            api_visibility="private",
            concurrency_limit=1,
            show_progress="full",
        )
