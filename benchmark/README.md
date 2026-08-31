# FigureFlow 提效实测包

这个目录用于比较三种技术绘图方式：

- `manual_docs`：在企业微信、飞书等文档工具里手工创建形状、连线和文字；
- `whole_image_edit`：先生成整张图，再通过局部编辑工具修正文字、箭头和版式；
- `figureflow`：用 FigureFlow 完成结构规划、无文字素材处理、确定性排版和导出。

这里没有预填任何耗时、准确率或“提效百分比”。`tasks.csv` 中的数字只描述任务结构，
`rubric.csv` 只定义如何测量。所有结论都必须来自录屏、时间戳和盲评记录支持的实测行。

## 文件说明

| 文件 | 用途 |
|---|---|
| `tasks.csv` | 3 个合成任务 × 3 种方法的 9 个实验条件 |
| `rubric.csv` | 指标的统一定义、单位和统计口径 |
| `results_template.csv` | 待填写的结果表；预置行状态均为 `planned`，不会进入统计 |
| `analyze_results.py` | 校验实测记录，并计算中位数、四分位距、成功率、错误数和配对比值 |
| `machine_cases.csv` | 5 个代表性合成案例；个人历史下界与机器任务定义在这里，未混入机器结果 |
| `case_plans/` | 可公开复现的已写入 FigurePlan；含标准、大字号和通用 GPU 绿色主题配置 |
| `run_machine_cases.py` | 从已写入计划到交付 ZIP 的确定性机器链路计时器 |
| `machine_results.csv` | 单次机器实测结果；只含机器计时、检查与产物哈希，不含人工耗时 |
| `analyze_machine_cases.py` | 校验机器证据，并生成严格分栏的 JSON/Markdown 摘要 |

## 推荐实验设计

最低限度是 1 名参与者完成 3 个任务 × 3 种方法。答辩前若时间允许，建议由至少 3 名参与者完成同一矩阵，并为每个“参与者 × 任务”随机化三种方法的顺序。三种方法必须使用同一份任务描述、验收清单、时间上限和本地修改要求。

为避免学习效应，可采用拉丁方或简单随机顺序。把实际顺序写入 `method_order`，不要照着模板行顺序直接做。评审最好只看到最终图和验收清单，不看到方法名称；是否做到盲评记录在 `reviewer_blinded`。

建议全程录屏，并保存：

1. 任务首次展示的时间点；
2. 首次达到统一验收清单的时间点；
3. 本地修改指令展示和完成的时间点；
4. 最终 SVG、PDF、PNG 或源文件；
5. 评审勾选表。

`evidence_uri` 可填写相对路径、内网链接或公开视频链接。提交答辩材料前请先脱敏。

## 填写结果

先复制模板，保留原模板不动：

```bash
cp benchmark/results_template.csv benchmark/results.csv
```

对每名参与者复制 9 个实验条件，随后填写：

- `measurement_status=measured`：实际执行且证据完整，进入统计；
- `measurement_status=excluded`：因中断、工具故障或流程偏离而排除，必须填写 `exclusion_reason`；
- `measurement_status=planned`：尚未执行，不进入统计。

实测行必须填写唯一的 `run_id`、参与者和评审代号、带时区的开始/结束时间、实际方法顺序、总耗时、主动操作时间、验收结果、语义检查数、错误数、可编辑交付结果和证据地址。

若在时间上限内没有合格版本，将 `acceptance_pass` 填为 `false`，并保持 `first_pass_seconds` 为空。若通过验收，则 `first_pass_seconds` 必须是正数且不大于 `total_elapsed_seconds`。

`pipeline_runtime_seconds` 仅记录 FigureFlow 流水线自身耗时。它不能与手工方法的主动操作时间直接对比，也不能单独证明人员提效。

## 指标口径

- 首个合格版本耗时：从任务首次展示到第一次满足全部验收项的墙钟时间。
- 主动人工操作时间：实际点击、拖拽、输入和修改的时间，排除模型或软件等待。
- 本地修改耗时：修改指令展示后，到修改版重新满足验收项的墙钟时间。
- 语义准确率：`semantic_items_correct / semantic_items_total`。
- 非目标稳定性：局部修改后，未要求变化且保持不变的项目数除以非目标项目总数。
- 文字/公式错误与版式缺陷：按 `rubric.csv` 逐项计数，不把同一缺陷重复计入两个类别。
- 可编辑交付：无需从头重做即可继续修改的交付物，填 `true`；只有扁平图片且必须重生成整图，填 `false`。

时间统一用秒，布尔值只用 `true` 或 `false`。缺失值保持为空，不要填 `0`、`N/A` 或估计值来代替没有测量的数据。

## 运行分析

```bash
python benchmark/analyze_results.py benchmark/results.csv \
  --json-out benchmark/analysis.json \
  --markdown-out benchmark/analysis.md
```

脚本会先验证列、任务/方法组合、唯一性、时间戳、数值范围和分子分母关系。发现无效实测行时会退出并列出具体行号，不会“修补”数据。

只有一条观测时会给出中位数，但四分位数和 IQR 标记为 `null`；至少两条观测才计算离散程度。FigureFlow 与基线的耗时比值采用严格配对：同一 `participant_id + task_id + trial_index` 同时存在两种方法且两个耗时都大于零时，才计算 `基线耗时 / FigureFlow 耗时`。比值大于 1 表示该次配对中 FigureFlow 更快。没有可配对数据时，报告只说明缺少数据，不生成比值。

对空模板运行脚本是安全的：输出状态为 `no_measured_data`，统计与比较均为空。

## 代表案例的机器链路实测

这组实测回答的是“已写入的结构计划进入公开确定性链路后，机器需要多长时间完成素材生成/抠图、排版、自动交付 QA 与打包”，不回答人工创作需要多久。它与上面的人工对照实验是两套数据，不能混为同一实验。

5 个代表案例覆盖日常汇报流程图、工厂机器人巡检 SOP、专利技术框架、论文机制图与 GPU 训练发布架构图。其中 C03 和 C05 使用 `presentation-spacious` 大字号预设；C05 同时使用通用 `gpu-green-tech` 主题。C02/C05 的计划分别保留 Public domain 与 CC BY 3.0 的 Wikimedia Commons 来源元数据，并使用仓库内已生成的 `robot_inspection` / `gpu_server` 局部语义素材；素材 provenance 会在运行前与计划交叉校验。所有输入均标记为 `synthetic-demo`，不冒充真实业务或科研结果。

运行：

```bash
python3 benchmark/run_machine_cases.py
python3 benchmark/analyze_machine_cases.py
```

默认把完整运行目录和大体积 ZIP 写入系统临时目录，只在 `benchmark/machine_evidence/` 保留脱敏、带 SHA-256 的小型 manifest，并在仓库保存 `machine_results.csv`、`machine_analysis.json` 和 `machine_analysis.md`。若要保留完整产物，可显式把 `--output-root` 指向仓库内的专用目录；提交前仍应评估仓库体积。

分析器会将结果行与当前 FigurePlan SHA-256、布局/主题配置、主题 token 哈希、渲染 manifest 快照、素材/输出哈希以及 QA 快照交叉校验。输入计划漂移或小型证据被局部篡改时，分析直接失败，不继续生成汇总结论。

每个案例只运行一次并保留原始墙钟数字，不报告均值、显著性或稳定性。计时器的精确定义是：

- 开始：读取并校验一个已经写入磁盘的 FigurePlan；
- 包含：生成通用 fallback 或读取仓库内已生成的局部语义素材、透明抠图、SVG/PDF/PNG 渲染、自动交付 QA、必需格式检查和关闭 ZIP；
- 结束：交付 ZIP 成功关闭；
- 不包含：自然语言规划、人工计划编写、参考图在线搜索、局部语义素材首次生成、人工语义评审、上传和 PPT 编辑；
- 自动 QA 只有在渲染 manifest 的 `layout_qa.ok` 和 PNG/PDF 输出审计同时通过时才记为通过，不等于语义正确率。

因此，C02/C05 证明的是“参考来源与许可可追溯、对应局部素材可在公开仓库复用，并能继续抠图/排版/QA”，不是在本次秒级计时中实时完成搜索和生图。若演示搜索与首次生成，应单独记录联网环境、模型版本、生成等待与失败重试。

`machine_cases.csv` 中的 3600 秒和 28800 秒来自用户在本次答辩准备对话中的个人历史经验下界：简单流程图至少 1 小时，论文级配图至少 1 个工作日，并以 8 小时作为下界。它们不是这些案例的同题人工现场计时。分析中只允许计算：

```text
相对个人自报下界的时间尺度倍率 = 个人自报历史下界 / 机器链路单次实测
```

展示时必须保留“≥”和完整边界：这个商只用于说明两个不同来源数字的时间尺度，**不是团队人效、不是同题人工计时、不是节省工时或因果提效结论**。若要陈述人效或节省，仍需完成 `results_template.csv` 定义的同题人工对照实验。

## 答辩中的表述边界

可以陈述 Demo 已实现的工作流、可编辑交付和单次流水线运行耗时。只有完成上述对照实验后，才能陈述“中位耗时降低”“成功率提高”或“错误数下降”。报告时同时给出样本数、IQR、失败数和原始证据，避免只展示最好的一次。
