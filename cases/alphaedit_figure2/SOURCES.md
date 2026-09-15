# AlphaEdit Figure 2：来源与数值审计

本案例复现《AlphaEdit: Null-Space Constrained Knowledge Editing for Language Models》的 Figure 2，固定使用 **arXiv:2410.02355v4**。它展示 LLaMA3 (8B) 在 2,000 个顺序编辑样本后的表现，是 11 组指标、5 种方法的环形分组柱状图。

## 来源优先级

1. **原始矢量 Figure 2**：从[官方 arXiv v4 TeX source](https://arxiv.org/src/2410.02355v4)取得 `figures/intro_part2.pdf`。源码 `chapters/1_intro.tex:29` 明确引用这一文件。其柱形、配色、标签和排版是本案例的视觉复现依据。
2. **论文正文与 Table 1**：使用[论文 v4](https://arxiv.org/abs/2410.02355v4)及源码 `chapters/5_exp.tex:20-31` 核对语境和数值。正文与图中有差异时，忠实复现保留 Figure 2 的可见标签，差异另行记录。
3. **作者官方实现**：[jianghoucheng/AlphaEdit](https://github.com/jianghoucheng/AlphaEdit)，检查版本 `b84624f44dfe8fc6cd9e41df916c44124a0c46dc`。该快照包含模型编辑、评估、GLUE 数据和结果汇总代码；未找到 Figure 2 的绘图脚本或已发布结果 CSV/JSON。此结论限于已检查的仓库快照。

## 数据与证据状态

`data.csv` 是 55 行长表，每一行对应一个指标和方法。字段 `value` 是可用于计算的数值，`label` 是原图显示字符串，`evidence_status` 固定为 `published-figure`。绘图时必须读取 `label`，保留 `5.90`、`0.90`、`1.80` 等尾零，避免默认数值格式改写。

`source` 中的 `arxiv:2410.02355v4/figures/intro_part2.pdf` 标识官方 v4 源码包内的图文件；下载地址见上文。所有数值均转录自已发表图中的标签，精度受标签的小数位限制，不代表恢复了未取整的原始实验日志。

本案例**没有重新运行 LLaMA3、AlphaEdit 或其他编辑方法**，也没有重新评测原论文结果。复现的是已发表图形及其可见数据。带星号的指标来自 ZsRE；不带星号的 Efficacy、Generalization、Specificity、Fluency、Consistency 来自 Counterfact；SST、RTE、CoLA 表示编辑后的通用能力评估。

## 原图与 Table 1 的差异

以下四处差异超过显示精度产生的普通取整差异：

| 方法 | 指标 | Figure 2 可见标签 | v4 Table 1 均值 |
|---|---|---:|---:|
| ROME | Fluency | 499.1 | 449.06 |
| PRUNE | Efficacy* | 0.17 | 24.77 |
| PRUNE | Generalization* | 0.24 | 23.87 |
| PRUNE | Specificity* | 0.89 | 20.69 |

本案例不推测差异原因，也不把表格数值悄悄替换进原图。完整对照保存在 `source_audit.json`。

## 几何与分析边界

原图混合了不同量纲和范围的指标，例如 Fluency 为数百，而 SST、RTE、CoLA 为 0 到 1 范围内的数值。原始柱形几何可用于视觉复现，但不能据此推导统一的径向归一化公式，或认为不同指标之间的柱长可直接比较。颜色和位置表达方法与指标身份，不提供跨指标可比性。

若用本案例模块分析新数据，应明确每个指标的定义、单位、方向与缩放规则，并使用真实数据来源。对本图的数值比较应限定在相同指标内；不能从不同指标的柱长或面积计算综合优劣。

## 许可、归属与校验

论文及其 arXiv v4 源图按 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 发布。复用源图及其改作时，应注明 Junfeng Fang、Houcheng Jiang 等作者、论文题名、版本、来源和许可，并标明 FigureFlow 做了程序化重建；这不表示原作者认可或参与 FigureFlow。

作者代码仓库采用 [MIT 许可](https://github.com/jianghoucheng/AlphaEdit/blob/b84624f44dfe8fc6cd9e41df916c44124a0c46dc/LICENSE)。代码许可与论文图像许可分别适用。

- 官方 v4 源码包 SHA-256：`55e3f23b097f52498edad8bf8fe294caf828741a4c2b1e1a892d2e5a9d428aaf`
- `figures/intro_part2.pdf` SHA-256：`a3f9f7293ecd91dc35d04d47ee17693ae87bfa0334cea169f06c990d2fd62921`

原始 PDF 由 Adobe Illustrator 26.0 (Windows) 生成，页面尺寸约 442.754 × 508.5 pt。中心文案的 PDF 文本提取包含全角逗号和感叹号；确切文本与元数据亦记录在 `source_audit.json`。
