# GPT-5.6-sol 在线示例

该目录来自一次真实 `gpt-5.6-sol` 语义规划与一次 `gpt-image-2` 无文字 Icon 生成。仓库代码仍使用官方 OpenAI Responses API 与默认 URL；本公开样例不记录实际服务路由、响应标识、token 数、原始提示词或绝对路径。

证据状态为 `implemented`：它证明工作流已经执行并通过三布局 QA，不证明团队提效比例。提效结论仍需按 `benchmark/` 的三方法同任务协议实测。

## 局部替换证明

[`local_edit_demo.html`](local_edit_demo.html) 对比原图与 [`figureflow_local_edit.svg`](figureflow_local_edit.svg)：仅在 [`figure_plan_local_edit.json`](figure_plan_local_edit.json) 中替换第 4 个节点的文字，复用原始 Icon、连接线和布局后重新渲染。节点 1、2、3、5 的语义、图标与顺序保持不变，用来展示相较整图重生成更可控的局部编辑路径。

![只修改第 4 个节点的前后对照](local_edit_proof.png)
