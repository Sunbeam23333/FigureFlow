# Example artifacts

## GPT-5.6-sol 在线样例

[`live_gpt56/`](live_gpt56/README.md) 来自一次真实 `gpt-5.6-sol` 语义规划与一次 `gpt-image-2` 无文字 Icon 生成，并通过三套布局的 PNG/PDF QA。目录同时提供：

- 最终 PNG、可编辑 SVG 与矢量 PDF；
- 实时 Icon 的 Chroma 原图、透明抠图和完整素材处理对照；
- 受约束 FigurePlan 与隐私最小化 Manifest。

公开导出已移除实际服务路由、响应标识、token 数、原始提示词、绝对路径和 PNG 元数据。

## 固定离线样例

这些文件来自一次 `offline` 固定预设复演，证据状态为 `synthetic-demo`：

- `figureflow_workflow.png`：适合 README 和答辩预览的 2700×1500 PNG；
- `figureflow_workflow.svg`：文字、连线和每个 `stage-*` 分组仍可编辑；
- `asset_pipeline.png`：原始 Chroma 素材与透明 soft matte 的并排记录；
- `figure_plan.json`：确定性 renderer 的受约束输入；
- `run_manifest.json`：本次运行的阶段耗时、文件哈希、QA 和证据边界。

这些文件不证明团队范围的效率提升。正式对比请使用 `benchmark/` 的统一任务、量表和录屏计时。
