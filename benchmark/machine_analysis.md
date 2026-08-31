# FigureFlow 代表案例机器链路实测

> **口径边界：** 个人自报历史下界与机器链路实测不是同类测量；不是团队人效、不是同题人工计时、不是节省工时或因果提效结论。

## 本次测量

- 代表案例：5 个；机器实测：5 次（每案例单次）。
- 链路成功：5/5；自动交付 QA 通过：5/5。
- 新版视觉链路覆盖：`presentation-spacious` 2 个案例；`gpu-green-tech` 1 个案例。
- 来源可追溯案例：2 个，共 2 条 Commons 参考元数据；渲染阶段不联网抓取。
- 计时范围：已写入 FigurePlan 到交付 ZIP 关闭；不含自然语言规划、人工计划编写、参考图在线搜索、局部语义素材首次生成、人工语义评审、上传和 PPT 编辑。
- 自动 QA 须同时通过渲染 manifest 的布局检查与 PNG/PDF 输出审计；语义质量未测量。
- 原始运行目录与大体积 ZIP 留在临时目录；仓库只保留脱敏 CSV、摘要和带哈希的小型 manifest。

| 代表任务 | 视觉配置 | 个人自报历史下界（非同题） | 机器 E2E 单次实测 | 时间尺度倍率* | 自动交付 QA | 输出 | 证据 |
|---|---|---:|---:|---:|---:|---|---|
| C01 线上故障处置周报流程 | academic-audit + standard | ≥1小时 | 1.358 秒 | ≥2650.9× | 通过 | MANIFEST/PDF/PNG/SVG/ZIP | [manifest](machine_evidence/20260831T180218Z-c01-11bfba8f.json) |
| C02 工厂机器人巡检SOP | academic-audit + standard | ≥1小时 | 1.737 秒 | ≥2072.6× | 通过 | MANIFEST/PDF/PNG/SVG/ZIP | [manifest](machine_evidence/20260831T180220Z-c02-0099f45f.json) |
| C03 多源数据融合专利框架 | academic-audit + presentation-spacious | ≥8小时（1个工作日下界） | 1.333 秒 | ≥21611.1× | 通过 | MANIFEST/PDF/PNG/SVG/ZIP | [manifest](machine_evidence/20260831T180221Z-c03-781f0a5e.json) |
| C04 教师—学生蒸馏机制图 | academic-audit + standard | ≥8小时（1个工作日下界） | 1.491 秒 | ≥19311.5× | 通过 | MANIFEST/PDF/PNG/SVG/ZIP | [manifest](machine_evidence/20260831T180223Z-c04-1032a0a4.json) |
| C05 GPU集群训练发布链路 | gpu-green-tech + presentation-spacious | ≥8小时（1个工作日下界） | 1.667 秒 | ≥17275.3× | 通过 | MANIFEST/PDF/PNG/SVG/ZIP | [manifest](machine_evidence/20260831T180224Z-c05-6879161e.json) |

\*“时间尺度倍率” = 个人自报历史下界 ÷ 机器链路实测，不是同题 speedup。个人下界来源于本次答辩准备对话；机器数字来自各行链接的带哈希 manifest。

## 机器时间汇总

- 最短 / 中位 / 最长：1.333 / 1.491 / 1.737 秒。
- 相对个人自报下界的时间尺度倍率范围：≥2072.6×–≥21611.1×。

## 尚未获得的证据

- 人工对照矩阵仍为 9 planned / 0 measured（来源：`benchmark/results_template.csv`）。
- 因此不能陈述团队人效提升、同题人工对照提速、节省工时、语义准确率提升或统计显著性。
