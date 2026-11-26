# 六篇论文 · 九张原图对照

这些是已运行的**分层重建**，不是整图截图，也不是作者的原始工程或新跑的实验。每张配方固定具体 PDF 的 SHA-256、页码、图框、色板、部件顺序和局限。重建侧用独立素材、SVG 图元和文字组装；原图侧从同一版本的论文单独裁出。图册按下表顺序排列，两侧按相同的论文实际宽度呈现。

| 论文 / 图 | 可以复用什么 | 哪些内容来自原作 |
|---|---|---|
| [VideoWorld Fig. 1](specs/videoworld_fig1.json) | 上方三种监督方式，下方围棋与机器人双轨；标签、箭头与胶片边缘 | 原图已压平。逐块提取案例和图标；播放标记仍随画面，不假装是独立矢量 |
| [Janus Fig. 1](specs/janus_fig1.json) | 左侧九轴雷达，右侧 3×5 样本网格；五个方法的色板 | 15 张原始样例；雷达轮廓来自图中的矢量路径，论文表值另外保存，不补造缺测值 |
| [Janus Fig. 2](specs/janus_fig2.json) | 理解与生成双分支，共享 Transformer，淡蓝与淡黄底色 | 原图是架构示意，没有案例照片；阴影近似 |
| [Epona Fig. 1](specs/epona_fig1.json) | 生成、轨迹控制、交通灯、规划四区；每个能力有自己的颜色 | 31 个原始图像实例，保留同条件不同结果的时间顺序与裁切 |
| [Epona Fig. 2](specs/epona_fig2.json) | 历史帧 → 时空骨干 → 视频和轨迹双头，跨模块反馈 | 4 个图像实例；复杂公式保留出版物轮廓，不是可改写的 LaTeX 表达式 |
| [GraphMimic Fig. 1](specs/graphmimic_fig1.json) | 三个任务逐帧叠图，下接四组基线比较；照片与图边分离 | 12 个照片底层，柱高依据论文表 1–4；两组仿真结果取五个任务列的算术平均 |
| [GraphMimic Fig. 2](specs/graphmimic_fig2.json) | 图生成与图引导策略双栏，观测与图节点对应 | 右上互相遮挡的三个未来图保留为一个可替换组合，没有推测遮挡区 |
| [Motus Fig. 1](specs/motus_fig1.json) | 视频、动作、理解三个专家通道，以及横跨三栏的注意力渐变 | 机器人帧、噪声图块和图标为原论文素材；渐变、字体和线宽有细微差异 |
| [DynaVieW Fig. 1](specs/dynaview_fig1.json) | 状态图像与转移描述交替，绿色/蓝色有固定语义 | 三个篮球关键帧和图像符号来自 PMLR 版第 1 页，并非新生成的视频 |

## 从新检出的仓库运行

也可[在 Colab 打开对照示例](https://colab.research.google.com/github/Sunbeam23333/FigureFlow/blob/main/cases/paper_rebuilds/review.ipynb)。运行后才获取公开论文和生成对照，notebook 本身不附带论文截图。

在仓库根目录执行。需要系统 Cairo；渲染不需要 API Key、不访问网络。若没有论文 PDF，可显式运行下载助手获取锁定版本。

```bash
python3 -m pip install -r cases/paper_rebuilds/requirements.txt
python3 cases/paper_rebuilds/render.py --list
python3 cases/paper_rebuilds/fetch_sources.py --all --source-dir cases/paper_rebuilds/local/sources
python3 cases/paper_rebuilds/render.py --all --source-dir cases/paper_rebuilds/local/sources
```

也可以将已取得的同版本 PDF 放在自己的目录，命名为 `videoworld.pdf`、`janus.pdf`、`epona.pdf`、`graphmimic.pdf`、`motus.pdf`、`dynaview.pdf`。单张例子：

```bash
python3 cases/paper_rebuilds/render.py --case epona_fig1 --source-dir /path/to/papers --output-dir /path/to/gallery
```

默认产物在本目录的 `local/`。打开 `index.html` 逐图看案例与色板，或打开 `figureflow_comparisons.pdf` 看九页等比例对照。每个案例目录有 `candidate.svg`、一页矢量 PDF、240 DPI PNG、`reference.png`、单页对照和 `provenance.json`。图册采用不同页面尺寸以保留原论文列宽，单栏小字不会人为放大成双栏。

## 把构图用于自己的研究

**TikZ 入口：** 每次重建也会写出 `candidate_tikz.tex`。在相应案例的输出目录运行 `xelatex -halt-on-error candidate_tikz.tex`，使用同目录的 `assets/` 即可另存为 `candidate_tikz.pdf`，不会覆盖 SVG 路径导出的 `candidate.pdf`。路径、结点、文字、裁切和图块均在 TeX 中独立绘制。九页主图册右侧统一使用 SVG 渲染；TikZ 的字体替代和渐变实现可能略有不同。

有 XeLaTeX 时，可在上面的 `--all` 命令后加 `--compile-tikz`，一并生成九份原生 TikZ PDF 和 `tikz_comparisons.pdf`（论文原图与实际编译结果逐页对照）。

- **换案例：** 复制生成的 SVG **及同级 `assets/`** 到新目录，替换其中一个有名字的 PNG。保持长宽比，视频序列注意时间对齐；来源和新的实验状态请重新记录。不要把作者案例标成自己的模型输出。
- **改构图：** 每个 SVG 部件都有 ID；可以独立改文本、移动照片和拖动路径。长期维护时改 JSON 后重建：坐标为 PDF 左上原点的 pt，`box` 表示原位裁切，`dest` 可指定新的位置。运行渲染器会覆盖它的输出，不要在唯一的手工编辑副本上重跑。
- **换色：** 每份配方的 `palette` 给出角色与十六进制色值；改主题时同步修改相应图层的 `fill` / `stroke` 或渐变色标。仅改调色板说明不会改变像素。
- **分清路径和数据：** `source_seqno` 指向指定版本 PDF 的一个绘制操作，重建时展开为可编辑的 SVG 曲线。图中曲线的位置和公式字形不等同于原始实验数组或数学源代码。`reported_values` 保存核过的表值，不会自动重算手工图形。

真实帧、原始论文和含原作的对照产物默认仅本地生成，不作为 FigureFlow 的 MIT 素材再发布。每份配方的 `url` 指向原始文件；复用作者的图片请保留署名、核对原论文及数据集的使用条件。

**本批验收：** 从空目录获取并校验六份论文；九张均做过并排目检。共有 113 个独立位图实例（包括案例和图标，不等于 113 个实验），其余为文字、几何或本地解析的矢量路径。九份 XeLaTeX 输出均为单页，例行检查包含画幅、缺字和文字溢出。要复跑真实 PDF 的集成测试，给 `FIGUREFLOW_PAPER_PDFS` 设置论文目录，再运行 `python3 -m unittest tests.test_layered_paper_rebuilds`。此验收不等于所有字体和像素相同，也不构成实验复现。
