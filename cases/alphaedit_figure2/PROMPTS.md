# 本次复现的提示词与执行记录

## 用户原始需求

> 参考这里的历史记录,我们的skill现在已经https://github.com/Sunbeam23333/FigureFlow传到这里了
> 然后我现在希望你集成一下数据分析和画数据图的能力,比如https://arxiv.org/pdf/2410.02355这里的Figure 2: Performance of various model editing methods on LLaMA3 (8B).
> 这张图我需要你1:1复现,然后把你复现过程中调用的所有代码和收到的提示词等全都复刻到figureflow中,让这个代码能跑出来alphaedit论文里这个图的效果

用户还提供了一条历史任务链接用于了解已有项目；公开文件不包含该私人任务记录。以上是本次实际收到的绘图需求，统一了链接格式和空白，未改变要求。这里公开的是任务提示词和可执行步骤，不是平台隐藏提示词或私有推理过程。

## 实际采用的复现决策

1. 读取 FigureFlow 历史和最新 main，继承完整来源、看图返修和可复演代码的要求。
2. 阅读 AlphaEdit 论文及官方源码，锁定 arXiv v4；优先查找独立 Figure 2，而不是从整页截图估数。
3. 核对 55 个可见数字、11 个指标、5 个方法，保留 `5.90`、`0.90` 等原始标签。发现与 Table 1 的四处实质冲突，保留 Figure 2 并单独记录冲突。
4. 作者未发布这张图的 Python 绘制脚本；独立源 PDF 为 Illustrator 导出。将原图矢量路径与逐字轮廓提取成 `scene.json`，为每根柱绑定 metric/method/value/label；这属于源图矢量数字化与重建，不伪称从 CSV 逆推出作者的原始程序。
5. 从 JSON 原语重新构建 SVG，再生成新 PDF/PNG。不得把参考 PDF/PNG 当最终输出；不得用 AI 生成数据、文字或坐标。
6. 相同渲染器、尺寸、DPI 比较参考图和新输出，记录完整像素与前景误差，不用大面积白色背景夸大相似度。
7. 另写真正数据驱动的同类环形柱状图和常规分面图。新数据不套固定原图几何；逐指标归一化明确标出，排名不跨量纲平均。

## 本轮实际分工提示（路径以仓库相对路径公开）

### 来源与数据核验

> 实现 cases/alphaedit_figure2/data.csv、source_audit.json、SOURCES.md。data.csv 为 55 行长表，字段 metric,method,value,label,source,evidence_status；保留每个原图精确标签字符串，evidence_status=published-figure。source_audit.json 去掉绝对机器路径，保留所有 4 处差异和版本、SHA256、许可证。SOURCES.md 用中文说明来源优先级、未复跑模型、原图几何不能推导出跨指标可比性、4处差异；引用官方 sources URL。注意 1:1 图可读标签 PRUNE Consistency 5.90；SST .90 和 Efficacy 98.9 不要以默认数字格式改写。

### 可复用数据分析

> 输入为 CSV 长表（metric,method,value，可含 label/source/evidence_status），只读本地用户文件。实现 validate/load（拒绝缺失/非有限/重复 metric+method，不悄悄插补），analyze（逐指标 method 排名、比最佳其他方法差值/相对差值，默认 higher-is-better 可按指标选择，绝不能平均不同量纲/虚构统计显著性），输出 JSON 和 Markdown 简洁审计。实现高质量数据驱动 grouped annular bar；使用 AlphaEdit 风格参考：白底、紫绿桃蓝棕、内圈曲线标签、中心标题、副标题、底部图例；每指标独立归一化最大，明确标注每指标独立缩放。可选常规 grouped bar small multiples 方便分析。数据图导出 vector PDF/SVG + PNG，使用 Matplotlib，无模型/API 调用。manifest 区分 published vs remeasured。

### 网页集成

> 新增分区名“数据分析与论文图复现”：离线一键 AlphaEdit Figure2 原图忠实矢量重建、PNG 预览、来源对照 preview、下载全部；另可上传 CSV（metric,method,value），标题与 focus method，运行数据校验排名和数据驱动环形柱状图。默认不调用 AI、不读取 Key、不联网；解释精确参考复刻与可变数据重绘是两个模式，不将已发表图数字当新实测。PUBLIC_DEMO 禁用上传只允许内置案例。每次 UUID run 子目录在 output_root/data；不可让用户指定输出路径，限制上传尺寸。

以上记录保留任务实质，省略了机器路径、并行工作协调和通用文件编辑要求；并非声称提供逐 token 的完整代理日志。

## 可直接复用的任务提示词

```text
请用 FigureFlow 复现指定论文的数据图。
先读取论文、独立矢量源图/数据表和作者代码，记录版本与哈希。
将原图数字与正文表格交叉核对；不一致时列出冲突，不自行修正。
若要求 1:1，保留图种、顺序、颜色、字体轮廓、尺寸、弧形标签与手工几何，
并明确该模式是否为源图数字化；禁止把复制原图当作独立绘图代码。
同时提供数据驱动绘图模式：替换长表数据后，按公开变换重新计算图形。
对缺失值、重复键、非有限值、量纲混合和无样本支撑的统计结论显式报错。
交付数据、可编辑源、全部脚本、提示词、来源/许可、PNG/SVG/PDF、
同尺寸的参考对比和误差报告。图形复现不等同于复跑模型实验。
```

## 模型/图像调用边界

本案例是在 Codex 会话中开发与审图的；离线复演脚本没有额外 LLM 或 ImageGen 请求，
因此没有需要的 API Key、生成随机种子或图像生成提示词。
不要为了“复刻模型调用”额外调用生图模型；数值和布局由这里的代码确定。
