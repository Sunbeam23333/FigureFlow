# 两种真实视频案例构图 · CVPR 2026 Figure 1

**要展示「改了什么条件，画面如何响应」**，用 [Edit-by-Track 的成对轨迹模板](track/README.md)。
**要展示「相同输入下，多种方法的画面和成本」**，用 [RAPID 的方法 × 帧位模板](rapid/README.md)。
本例不是视频模型复现：帧、投影和数值是论文作者发表的证据。没有运行模型、补画帧或推测未刊出的时间戳。

## 两页并排 PDF

在 FigureFlow 仓库根目录运行。需要 Python、XeLaTeX 和常规 TeX Live 包（standalone、TikZ、Latin Modern）。
不需要 GPU、API Key 或生成式绘图服务。只有显式的 `fetch` 联网；也可自行放置同版本的 `track.pdf` 和 `rapid.pdf`。

```sh
python3 -m pip install -r cases/cvpr26_video_pairs/requirements.txt
python3 cases/cvpr26_video_pairs/review.py fetch --source-dir cases/cvpr26_video_pairs/local/sources
python3 cases/cvpr26_video_pairs/review.py build --source-dir cases/cvpr26_video_pairs/local/sources --output-dir cases/cvpr26_video_pairs/local/proof
```

打开 `local/proof/figureflow-video-fig1-comparison.pdf`。第一页 Edit-by-Track，第二页 RAPID；
两侧按**各自论文的实际图宽**排版，左侧为原图，右侧为独立重建的展示稿。
两页的 240 dpi 纸面预览、独立图层工作稿和验收报告 `acceptance.json` 在同一目录。
构建失败不发布半本图册，已有交付不会被覆盖；再次试验请换一个输出目录。

| | 忠实展示稿 | 可编辑工作稿 | 不要据此推断 |
|---|---|---|---|
| [Edit-by-Track · Lee 等](https://openaccess.thecvf.com/content/CVPR2026/papers/Lee_Generative_Video_Motion_Editing_with_3D_Point_Tracks_CVPR_2026_paper.pdf#page=1) | 从空白页面按绘制顺序装配 24 个帧图像、2 个轨迹投影和原生图形/文字；482 bp 宽 | `track/scene.json` 与 `materials.pdf`；可单独替换、移动具名部件，保留其他帧和遮挡 | 出版的二维投影不是可还原的原始三维点集；三帧叠片不是带时间戳的完整视频 |
| [RAPID · Lin 等](https://openaccess.thecvf.com/content/CVPR2026/papers/Lin_RAPID_Reusing_Attention_Sparsity_with_Inter-step_Adaptation_for_Efficient_Video_CVPR_2026_paper.pdf#page=1) | 原论文整张是 JPEG。由 15 个独立帧块、46 个文字块和近白色压缩残差无损拼合成 `rapid/seamless.pdf`，不是把原 JPEG 放回右栏；约 494.95 bp 宽 | `rapid/layout.json`、逐帧 PNG、可独立移动的 `reconstruction.pdf`、单词轮廓 `vectors.pdf` 和重新排字的 `native.pdf` | 五列为发表的对应帧位，不是秒数。PSNR、延迟和加速比对应[表 1 的基准评测](https://openaccess.thecvf.com/content/CVPR2026/papers/Lin_RAPID_Reusing_Attention_Sparsity_with_Inter-step_Adaptation_for_Efficient_Video_CVPR_2026_paper.pdf#page=7)，不属于这个宇航员片段的单独评分 |

## 验收：具体哪些东西不能变？

1. **参照独立。** 先核对[官方版本、来源和 SHA-256](sources.json)。把整篇论文第一页另外裁切并在 300 dpi 渲染，必须和左侧独立参考图逐像素相同。右侧不能用原图整图充当素材。
2. **逐项对齐。** 轨迹图核对 26 次贴图的顺序、仿射变换和软遮罩，特别是估计／已编辑投影不能对调；三对下方案例不能串组。视频矩阵逐格核对 RGB 哈希、行身份、列序和边界：首列 402 px，余列各 413 px，四条间隙各 2 px，不可五等分。
3. **颜色与数字。** RAPID 保留原印刷字的黑、红、绿及压缩边缘，另存可以替换内容的排字版。图中的四舍五入值与表 1 的精度分别保留，替换成自己的结果时必须更换数据来源。轨迹投影随原有颜色和透明蒙版一起使用，不从颜色反推物理量。
4. **检查最终页面。** 验收分区包括两幅轨迹、两端叠片和三个案例对，或十五个帧区、三行指标和共享提示词。检查 144 和 300 dpi；固定版展示稿在锁定的 MuPDF 下要求 300 dpi 像素完全一致。最终 TeX 纸面还要核对每个挂载图像的位置/尺寸（容差 0.08 bp），并检查版宽下的实际页面。
5. **声明适用范围。** RAPID 在原始 2062 × 1016 格点重组后 RGB 完全一致；不同阅读器、缩放和 JPEG 降采样可以带来差异。拆为独立对象的工作稿以及更换字形后的排字版**不承诺像素相同**。换帧或改字后，应该验证未改部件和新素材来源，不再沿用原论文的 1:1 结论。

本批实测（展示稿单独按论文宽度渲染）：在 MuPDF 240/300 dpi 下，两张图均为 0 个不同像素。
Poppler 240 dpi 的 Edit-by-Track 也完全一致；Poppler 300 dpi 的 RAPID 仅 4 个像素有 1/255 的通道差。
这些是特定渲染器和分辨率的对照记录，不是通用美学分。

如已安装开发依赖，用下面的命令同时运行真实论文集成测试、合册失败回滚测试和两个模板的换帧测试：

```sh
FIGUREFLOW_CVPR26_PDFS=cases/cvpr26_video_pairs/local/sources python3 -m pytest --import-mode=importlib tests/test_cvpr26_video_pairs.py cases/cvpr26_video_pairs/track/test_replay.py cases/cvpr26_video_pairs/rapid/test_replay.py
```

设计取舍：采纳 [CadFlow #13](https://github.com/yhz5613813/CadFlow/pull/13/files) 中单独交付忠实展示和可编辑来源的做法，以及 [FigMirror #9](https://github.com/VILA-Lab/FigMirror/pull/9/files) 的「列出参考部件／记录必须保留之处」思路。没有引入外部 PR 的代码或美学总分。

仓库只发布模板、验收代码和来源记录；带原作的图册、帧、印刷字块、字体子集和论文 PDF 在本地按需生成，不随 FigureFlow 的 MIT 许可分发。
