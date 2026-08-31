"""FigureFlow Gradio demo: brief → plan → icons → editable technical figure."""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path

import gradio as gr

from demo_core.pipeline import OUTPUT_ROOT, RunResult, run_pipeline
from demo_core.reference_search import search_references
from demo_core.schemas import ReferenceAsset


DEFAULT_BRIEF = """请把下面的内部高频画图流程做成一张适合汇报投屏的中文技术流程图：
1. 从一段业务描述中提炼 3–6 个节点、因果关系和证据状态；
2. 为每个节点生成不含文字的独立语义 Icon；
3. 用色键抠图得到透明素材；
4. 程序写入准确中文、箭头和版式；
5. 自动检查边界、字体与单页 PDF，并导出 SVG、PDF、PNG。
不能虚构提效比例；必须把演示数据标为“合成演示”。"""

MODE_MAP = {
    "自动：有 Key 在线，否则离线复演": "auto",
    "在线：强制 GPT-5.6-sol": "online",
    "离线：稳定复演预设": "offline",
}
PUBLIC_DEMO = os.getenv("FIGUREFLOW_PUBLIC_DEMO", "false").lower() == "true"
LOGGER = logging.getLogger("figureflow")
MODE_LABEL_BY_VALUE = {value: label for label, value in MODE_MAP.items()}
LAYOUT_MAP = {
    "由 GPT 选择": None,
    "横向流程 · ribbon": "ribbon",
    "中心强调 · bowtie": "bowtie",
    "交错推进 · dual-rail": "dual-rail",
}
LAYOUT_PRESET_MAP = {
    "标准排版 · standard": "standard",
    "投屏大字 · presentation-spacious": "presentation-spacious",
}
THEME_MAP = {
    "Academic Audit": "academic-audit",
    "GPU Systems Green（通用非官方）": "gpu-green-tech",
}
REFERENCE_PROVIDER_MAP = {
    "离线示例（默认，不联网）": "offline-example",
    "Wikimedia Commons（固定接口，仅元数据）": "wikimedia-commons",
    "用户 URL（只记录，不抓取）": "user-url",
}


def _reference_summary(assets: list[ReferenceAsset]) -> str:
    if not assets:
        return "**参考来源：** 未选择结果。渲染器不会自动下载第三方素材。"
    rows = ["**参考来源（metadata-only；不会自动下载图片）**", ""]
    for index, asset in enumerate(assets, start=1):
        title = html.escape(asset.title)
        source_url = asset.source_url if asset.source_url and asset.source_url.startswith(("http://", "https://")) else None
        license_url = asset.license_url if asset.license_url and asset.license_url.startswith(("http://", "https://")) else None
        title_html = (
            f'<a href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener noreferrer">{title}</a>'
            if source_url
            else title
        )
        author = html.escape(asset.author or "作者未标注")
        license_name = html.escape(asset.license_name or "许可证待人工核验")
        license_html = (
            f'<a href="{html.escape(license_url, quote=True)}" target="_blank" rel="noopener noreferrer">{license_name}</a>'
            if license_url
            else license_name
        )
        rows.append(f"{index}. {title_html} · {author} · {license_html} · `{asset.provider}`")
    rows.extend(["", "> 这些条目只作为构图参考和溯源 metadata 写入 FigurePlan / Manifest；当前 Demo 不下载或合成第三方图片。"])
    return "\n".join(rows)


def _resolve_references(provider_label: str, query: str, user_urls_text: str) -> list[ReferenceAsset]:
    provider = "offline-example" if PUBLIC_DEMO else REFERENCE_PROVIDER_MAP[provider_label]
    user_urls = tuple(line.strip() for line in user_urls_text.splitlines() if line.strip())
    return search_references(
        query,
        provider=provider,
        limit=3,
        user_urls=() if PUBLIC_DEMO else user_urls,
    )


def _preview_references(provider_label: str, query: str, user_urls_text: str):
    try:
        assets = _resolve_references(provider_label, query, user_urls_text)
    except Exception as exc:
        LOGGER.warning("Reference preview failed: %s", type(exc).__name__)
        return "**参考检索失败。** 请检查查询词、URL 或网络后重试。", []
    return _reference_summary(assets), [asset.model_dump() for asset in assets]


def _metrics_markdown(result: RunResult) -> str:
    metrics = result.metrics
    return f"""
| 本次运行阶段 | 耗时 |
|---|---:|
| 语义规划 | {metrics['planning_ms'] / 1000:.2f} s |
| 实时 Icon 生成 | {metrics['icon_generation_ms'] / 1000:.2f} s |
| 抠图与素材处理 | {metrics['cutout_ms'] / 1000:.2f} s |
| 三套布局渲染 | {metrics['render_3_layouts_ms'] / 1000:.2f} s |
| 自动 QA | {metrics['qa_ms'] / 1000:.2f} s |
| 交付包压缩 | {metrics['packaging_ms'] / 1000:.2f} s |
| **端到端总耗时** | **{metrics['total_ms'] / 1000:.2f} s** |

> 这里只记录本次 Demo 的机器耗时，不等同于团队提效比例。正式数字需与手工拉线、整图生成后二次编辑做同任务对照。
"""


def _run_demo(
    brief: str,
    mode_label: str,
    layout_label: str,
    layout_preset_label: str,
    theme_label: str,
    live_icon: bool,
    reference_provider_label: str,
    reference_query: str,
    user_urls_text: str,
):
    if PUBLIC_DEMO:
        brief = DEFAULT_BRIEF
        mode_label = "离线：稳定复演预设"
        live_icon = False
    try:
        references = _resolve_references(reference_provider_label, reference_query, user_urls_text)
        result = run_pipeline(
            brief,
            mode=MODE_MAP[mode_label],
            layout_override=LAYOUT_MAP[layout_label],
            layout_preset_override=LAYOUT_PRESET_MAP[layout_preset_label],
            theme_override=THEME_MAP[theme_label],
            live_icon=live_icon,
            reference_assets=references,
        )
    except Exception as exc:
        # Keep public logs useful without persisting SDK exception text, which may
        # contain request identifiers or a deployment-specific service URL.
        LOGGER.error("FigureFlow run failed: %s", type(exc).__name__)
        message = "运行失败（PIPELINE_FAILED）。请检查服务端日志、字体与 API 配置。"
        return (
            f"### 运行失败\n\n{message}",
            "",
            {},
            [],
            None,
            None,
            None,
            None,
            None,
            None,
            "**参考来源：** 运行失败，未写入交付。",
            [],
        )
    public_notice = "公开安全模式：固定合成示例 · " if PUBLIC_DEMO else ""
    status = (
        f"### {public_notice}{result.notice}\n\n运行编号：`{result.run_id}` · 最终布局：`{result.selected_layout}`"
        f" · 主题：`{THEME_MAP[theme_label]}` · 字号版式：`{LAYOUT_PRESET_MAP[layout_preset_label]}`"
    )
    downloads = [result.final_svg, result.final_pdf, result.bundle_zip, result.manifest]
    return (
        status,
        _metrics_markdown(result),
        result.plan,
        result.candidates,
        result.raw_preview,
        result.processed_preview,
        result.contact_sheet,
        result.final_png,
        downloads,
        result.qa,
        _reference_summary(references),
        [asset.model_dump() for asset in references],
    )


CSS = """
.gradio-container { max-width: 1440px !important; }
.hero { padding: 28px 30px; border-radius: 24px; color: white;
  background: radial-gradient(circle at 90% 0%, #2f75c8 0, transparent 36%),
              linear-gradient(120deg, #102944, #174d72 58%, #16827a); }
.hero, .hero * { color: #FFFFFF !important; }
.hero h1 { margin: 0 0 8px; font-size: 34px; letter-spacing: -0.5px; }
.hero p { margin: 0; opacity: .92; font-size: 17px; }
.badge { display: inline-block; margin-bottom: 14px; padding: 5px 11px; border-radius: 99px;
  background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.24); font-size: 13px; }
.flow-card { border-radius: 18px !important; }
"""


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="FigureFlow") as demo:
        gr.HTML(
            """<div class="hero"><div class="badge">Tencent conversion defense · AI automation demo</div>
            <h1>FigureFlow：让 AI 规划，让程序把图画对</h1>
            <p>业务描述 → 结构化 FigurePlan → 无文字语义 Icon → 透明抠图 → 矢量文字与连线 → QA 与多格式导出</p></div>"""
        )
        gr.Markdown(
            "**为什么不用整图生成？** 技术图同时要求语义正确、中文准确、局部可改和稳定复现。FigureFlow 把高不确定的视觉生成限制在无文字组件，把文字、箭头、版式和证据标注交给确定性程序。"
        )
        with gr.Row(equal_height=False):
            with gr.Column(scale=5, elem_classes="flow-card"):
                brief = gr.Textbox(label="① 输入业务描述", value=DEFAULT_BRIEF, lines=7, max_lines=14, interactive=not PUBLIC_DEMO)
                configured_mode = os.getenv("DEMO_MODE", "auto")
                mode = gr.Radio(
                    list(MODE_MAP),
                    value=("离线：稳定复演预设" if PUBLIC_DEMO else MODE_LABEL_BY_VALUE.get(configured_mode, list(MODE_MAP)[0])),
                    label="运行模式",
                    interactive=not PUBLIC_DEMO,
                )
                with gr.Row():
                    layout = gr.Dropdown(list(LAYOUT_MAP), value=list(LAYOUT_MAP)[0], label="布局选择")
                    layout_preset = gr.Dropdown(
                        list(LAYOUT_PRESET_MAP),
                        value="投屏大字 · presentation-spacious",
                        label="字号版式",
                    )
                theme = gr.Dropdown(list(THEME_MAP), value=list(THEME_MAP)[0], label="主题配色")
                live_icon = gr.Checkbox(
                    label="在线时额外实时生成 1 个 Icon（更慢、产生图像费用）",
                    value=False,
                    interactive=not PUBLIC_DEMO,
                )
                with gr.Accordion("真实参考检索（可选）", open=True):
                    reference_choices = [next(iter(REFERENCE_PROVIDER_MAP))] if PUBLIC_DEMO else list(REFERENCE_PROVIDER_MAP)
                    reference_provider = gr.Dropdown(
                        reference_choices,
                        value=reference_choices[0],
                        label="参考来源 Provider",
                        interactive=not PUBLIC_DEMO,
                    )
                    reference_query = gr.Textbox(
                        label="检索词（Wikimedia Commons）",
                        value="GPU cluster data centre",
                        interactive=not PUBLIC_DEMO,
                    )
                    user_urls = gr.Textbox(
                        label="用户参考 URL（每行一个；只记录、不抓取）",
                        lines=2,
                        placeholder="https://example.org/reference.png",
                        interactive=not PUBLIC_DEMO,
                    )
                    preview_references = gr.Button("预览来源 metadata", size="sm")
                run_button = gr.Button("生成可编辑技术图", variant="primary", size="lg")
                gr.Markdown(
                    "密钥只从服务端环境变量读取，不会进入浏览器或运行清单。GPU Systems Green 是通用加速器技术配色，不使用第三方 Logo，也不暗示背书或关联。"
                )
            with gr.Column(scale=7):
                status = gr.Markdown("### 等待运行")
                metrics = gr.Markdown()
                plan = gr.JSON(label="② 受约束 FigurePlan（在线 GPT / 离线预设）")
                reference_summary = gr.Markdown("**参考来源：** 等待预览。")
                with gr.Accordion("参考 metadata（将写入 FigurePlan / Manifest）", open=False):
                    reference_metadata = gr.JSON()

        gr.Markdown("## ③ 布局候选")
        gallery = gr.Gallery(label="相同语义、三种确定性布局", columns=3, height=350, object_fit="contain")
        gr.Markdown("## ④ 素材生成与透明抠图")
        with gr.Row():
            raw = gr.Image(label="原始 Chroma 素材", type="filepath", height=300)
            processed = gr.Image(label="Soft matte + despill", type="filepath", height=300)
            contact_sheet = gr.Image(label="全部素材处理记录", type="filepath", height=300)
        gr.Markdown("## ⑤ 精确文字排版、质量门禁与交付")
        final = gr.Image(label="最终图（PNG 预览；SVG/PDF 可继续编辑）", type="filepath")
        downloads = gr.File(label="下载 SVG / PDF / ZIP / Manifest", file_count="multiple")
        with gr.Accordion("自动 QA 报告", open=False):
            qa = gr.JSON()

        preview_references.click(
            _preview_references,
            inputs=[reference_provider, reference_query, user_urls],
            outputs=[reference_summary, reference_metadata],
        )

        run_button.click(
            _run_demo,
            inputs=[
                brief,
                mode,
                layout,
                layout_preset,
                theme,
                live_icon,
                reference_provider,
                reference_query,
                user_urls,
            ],
            outputs=[
                status,
                metrics,
                plan,
                gallery,
                raw,
                processed,
                contact_sheet,
                final,
                downloads,
                qa,
                reference_summary,
                reference_metadata,
            ],
        )
    return demo


demo = build_demo()


if __name__ == "__main__":
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    auth_user = os.getenv("FIGUREFLOW_BASIC_AUTH_USER")
    auth_password = os.getenv("FIGUREFLOW_BASIC_AUTH_PASSWORD")
    auth = (auth_user, auth_password) if auth_user and auth_password else None
    demo.queue(default_concurrency_limit=1, max_size=8).launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        share=os.getenv("GRADIO_SHARE", "false").lower() == "true",
        allowed_paths=[str(Path(OUTPUT_ROOT).resolve())],
        theme=gr.themes.Soft(primary_hue="blue", secondary_hue="teal"),
        css=CSS,
        auth=auth,
    )
