"""Local-only Gradio entry points for published-figure replay and CSV charts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Mapping
import uuid

import gradio as gr
from gradio.processing_utils import get_upload_folder


MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_REPORT_BYTES = 1024 * 1024
DEFAULT_CHART_TITLE = "Model editing performance"
ARTIFACT_KEYS = ("png", "pdf", "svg", "comparison", "report", "manifest", "data", "zip")


class DataUIError(ValueError):
    """A validation message that may be shown directly in the UI."""


def _public_demo(value: bool | None) -> bool:
    return os.getenv("FIGUREFLOW_PUBLIC_DEMO", "false").lower() == "true" if value is None else value


def _failure(message: str, *, error_type: str = "validation_error") -> tuple:
    return (
        f"### 未生成图表\n\n{message}", None, None, [],
        {"status": "error", "error_type": error_type},
    )


def _run_directory(output_root: str | Path, mode: str) -> Path:
    directory = Path(output_root).resolve() / "data" / f"{mode}-{uuid.uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def _validated_artifacts(result: Mapping[str, object], run_dir: Path, *, required: set[str]) -> dict[str, str]:
    artifacts = {}
    for key in ARTIFACT_KEYS:
        value = result.get(key)
        if not value:
            continue
        if not isinstance(value, (str, Path)):
            raise DataUIError("生成器返回了无效的交付文件。")
        path = Path(value)
        if not path.is_absolute():
            path = run_dir / path
        path = path.resolve(strict=True)
        if run_dir not in path.parents or not path.is_file():
            raise DataUIError("生成器返回了本次运行目录之外的文件。")
        artifacts[key] = str(path)
    if not required.issubset(artifacts):
        raise DataUIError("生成结果不完整，请查看服务端运行记录。")
    return artifacts


def _report_payload(artifacts: Mapping[str, str]) -> dict:
    report_path = artifacts.get("report")
    if not report_path:
        return {"status": "completed"}
    report = Path(report_path)
    if report.stat().st_size > MAX_REPORT_BYTES:
        return {"status": "completed", "note": "报告较大，请下载完整文件。"}
    text = report.read_text(encoding="utf-8")
    if report.suffix.lower() == ".json":
        value = json.loads(text)
        return value if isinstance(value, dict) else {"results": value}
    return {"summary": text}


def _completed(message: str, artifacts: Mapping[str, str], run_dir: Path) -> tuple:
    downloads = [artifacts[key] for key in ARTIFACT_KEYS if key in artifacts]
    return (
        f"### {message}\n\n运行编号：`{run_dir.name}` · 本地确定性运行 · 未调用 AI",
        artifacts["png"], artifacts.get("comparison"), downloads, _report_payload(artifacts),
    )


def run_published_reproduction(
    *, output_root: str | Path, reproduction_runner: Callable | None = None,
) -> tuple:
    """Replay the bundled AlphaEdit figure; no upload, URL, key, or model input."""
    try:
        if reproduction_runner is None:
            from .alphaedit_reproduction import run_reproduction

            reproduction_runner = run_reproduction
        run_dir = _run_directory(output_root, "alphaedit")
        result = reproduction_runner(run_dir)
        artifacts = _validated_artifacts(result, run_dir, required=set(ARTIFACT_KEYS))
        return _completed(
            "AlphaEdit Figure 2 复现完成：已发表图的矢量重建", artifacts, run_dir,
        )
    except DataUIError as exc:
        return _failure(str(exc))
    except Exception as exc:
        return _failure(
            "原图复现未完成，请检查本地依赖与内置案例文件。", error_type=type(exc).__name__,
        )


def _read_csv_upload(value: str | Path | None, *, upload_root: str | Path | None) -> bytes:
    if not value:
        raise DataUIError("请上传包含 metric、method、value 三列的 CSV。")
    root = Path(upload_root or get_upload_folder()).resolve()
    try:
        path = Path(value).resolve(strict=True)
    except (OSError, ValueError, TypeError) as exc:
        raise DataUIError("无法读取上传的文件，请重新上传。") from exc
    if root not in path.parents:
        raise DataUIError("仅接受通过当前页面上传的 CSV 文件。")
    if not path.is_file() or path.suffix.lower() != ".csv":
        raise DataUIError("请上传 .csv 文件。")
    if not 0 < path.stat().st_size <= MAX_CSV_BYTES:
        raise DataUIError("CSV 不能为空，且最大为 2 MB。")
    with path.open("rb") as stream:
        data = stream.read(MAX_CSV_BYTES + 1)
    if not 0 < len(data) <= MAX_CSV_BYTES:
        raise DataUIError("CSV 不能为空，且最大为 2 MB。")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataUIError("CSV 需要使用 UTF-8 编码。") from exc
    return data


def _label(value: str | None, *, name: str, default: str, maximum: int) -> str:
    text = (value or default).strip()
    if not text or len(text) > maximum or any(ord(character) < 32 for character in text):
        raise DataUIError(f"{name}需要是 1–{maximum} 字符的单行文字。")
    return text


def run_csv_analysis(
    upload: str | Path | None,
    title: str = DEFAULT_CHART_TITLE,
    focus_method: str = "AlphaEdit",
    *,
    output_root: str | Path,
    public_demo: bool | None = None,
    upload_root: str | Path | None = None,
    chart_renderer: Callable | None = None,
) -> tuple:
    """Validate a page upload and render a new chart from its numerical values."""
    if _public_demo(public_demo):
        return _failure("公开演示仅开放内置 AlphaEdit 案例，CSV 上传已停用。")
    try:
        chart_title = _label(title, name="标题", default=DEFAULT_CHART_TITLE, maximum=160)
        focus = _label(focus_method, name="重点方法", default="AlphaEdit", maximum=80)
        content = _read_csv_upload(upload, upload_root=upload_root)
        if chart_renderer is None:
            from .data_analysis import render_annular_chart

            chart_renderer = render_annular_chart
        run_dir = _run_directory(output_root, "csv")
        source = run_dir / "input.csv"
        source.write_bytes(content)
        result = chart_renderer(source, run_dir, title=chart_title, focus_method=focus)
        artifacts = _validated_artifacts(result, run_dir, required={"png", "pdf", "svg", "report", "manifest"})
        artifacts.setdefault("data", str(source))
        return _completed("CSV 数据分析与环形柱状图完成", artifacts, run_dir)
    except DataUIError as exc:
        return _failure(str(exc))
    except Exception as exc:
        return _failure(
            "数据分析未完成。请核对 CSV 列名、有限数值、重复项与各方法的指标完整性。",
            error_type=type(exc).__name__,
        )


def build_data_section(*, output_root: str | Path, public_demo: bool) -> None:
    with gr.Accordion("数据分析与论文图复现", open=False):
        gr.Markdown(
            "**两种模式，全程在本地运行。** 原图复现重建 AlphaEdit 论文 Figure 2 的矢量外观；"
            "CSV 模式根据新数据完成校验、排名与环形柱状图重绘。"
            "论文中的已发表数值保留来源，不计作本次新实验；两个模式均不调用 AI、不读取 Key、不联网。"
        )
        with gr.Tabs():
            with gr.Tab("AlphaEdit Figure 2 原图复现"):
                gr.Markdown(
                    "**Performance of various model editing methods on LLaMA3 (8B).** "
                    "点击后生成 SVG / PDF / PNG、来源对照、分析报告、数据与完整下载包。"
                    "复现使用随仓库保存的参考几何与来源信息。"
                )
                replay = gr.Button("离线复现 AlphaEdit Figure 2", variant="primary")
            with gr.Tab("上传 CSV · 数据分析与重绘"):
                gr.Markdown(
                    "CSV 格式：`metric,method,value`，UTF-8，最大 2 MB。"
                    "每行给出一个方法在一个指标上的数值；图形由这些数值重新计算。"
                    + ("\n\n**公开演示模式：上传与自定义绘图已停用。**" if public_demo else "")
                )
                upload = gr.File(
                    label="上传数据 CSV", file_count="single", file_types=[".csv"],
                    type="filepath", interactive=not public_demo,
                )
                with gr.Row():
                    title = gr.Textbox(
                        label="图标题", value=DEFAULT_CHART_TITLE, max_length=160,
                        interactive=not public_demo,
                    )
                    focus = gr.Textbox(
                        label="重点显示的方法", value="AlphaEdit", max_length=80,
                        interactive=not public_demo,
                    )
                analyze = gr.Button("校验数据并绘图", variant="primary", interactive=not public_demo)
        status = gr.Markdown("尚未运行。")
        with gr.Row():
            preview = gr.Image(label="生成图预览", type="filepath", interactive=False)
            comparison = gr.Image(label="原图与复现对照（内置案例）", type="filepath", interactive=False)
        downloads = gr.File(label="下载全部产物（含完整 ZIP）", file_count="multiple", interactive=False)
        with gr.Accordion("分析与复现报告", open=False):
            report = gr.JSON()
        outputs = [status, preview, comparison, downloads, report]
        replay.click(
            lambda: run_published_reproduction(output_root=output_root),
            inputs=[], outputs=outputs, api_name=False, api_visibility="private",
            concurrency_limit=1, concurrency_id="data-chart", show_progress="full",
        )
        analyze.click(
            lambda csv, chart_title, focus_method: run_csv_analysis(
                csv, chart_title, focus_method, output_root=output_root, public_demo=public_demo,
            ),
            inputs=[upload, title, focus], outputs=outputs, api_name=False, api_visibility="private",
            concurrency_limit=1, concurrency_id="data-chart", show_progress="full",
        )
