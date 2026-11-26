# Third-party notices

FigureFlow is distributed under the MIT License, but it uses third-party software that remains subject to its own license. This notice is informational and does not replace the license text shipped by each dependency.

## Direct Python dependencies

| Component | Purpose | License commonly distributed with the package |
|---|---|---|
| OpenAI Python SDK | Responses API client | Apache License 2.0 |
| Gradio | Local web interface | Apache License 2.0 |
| Pydantic | Structured plan validation | MIT License |
| NumPy | Image and numeric operations | BSD 3-Clause License |
| pandas | Tabular figure inputs | BSD 3-Clause License |
| Matplotlib | Deterministic charts | Matplotlib License (PSF/BSD-style) |
| Pillow | Image loading and export | HPND License |
| CairoSVG | SVG to PDF/PNG conversion | GNU LGPL v3 or later |
| PyYAML | YAML configuration | MIT License |
| pypdf | Reconstructed PDF metadata and source attachments | BSD 3-Clause License; [upstream license](https://github.com/py-pdf/pypdf/blob/main/LICENSE) |

The optional `digitize` extra installs PyMuPDF for regenerating the AlphaEdit vector scene from the official PDF (and it can serve as an alternative rasterizer). PyMuPDF/MuPDF are available under open-source AGPL or a commercial license, as documented in the [upstream licensing notice](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright). This optional dependency is not covered by FigureFlow's MIT license. The regular reproduction path uses the committed scene, CairoSVG and Poppler and does not require installing PyMuPDF.

The exact version resolved during installation is authoritative. Review the installed distribution metadata and bundled license files before redistribution, especially when packaging a closed-source service.

## Container and optional system components

The provided container may install the following Debian packages:

- Cairo and Pango runtime libraries, distributed under their respective LGPL licenses;
- Noto CJK fonts, distributed under the SIL Open Font License 1.1.
- Poppler command-line tools and libraries, distributed under the GNU GPL v2 or later.

The extended research-figure skill can optionally use XeLaTeX/TeX Live. TeX Live is not installed by the default lightweight Demo image. If you add it to a redistributed image, include its license texts and comply with its package-specific terms.

## Fonts and visual assets

FigureFlow does not bundle proprietary fonts such as Arial, Comic Sans, PingFang, or Microsoft YaHei. CairoSVG is given one concrete host CJK family because its fallback behavior is not reliable; the default container installs Noto CJK, while local macOS/Windows runs use an available system family. PDF QA rejects output when no recognized embedded CJK font is found.

Files under `assets/icons/raw/` are generated demonstration assets. Their inclusion under this repository's license does not grant rights in third-party trademarks, characters, logos, training data, or source references that a user may introduce in later generations. Keep prompt and provenance records, and review generated output before commercial or public use.

## AlphaEdit published-figure case

The case in `cases/alphaedit_figure2/` derives from Figure 2 of *AlphaEdit: Null-Space Constrained Knowledge Editing for Language Models*, by Junfeng Fang, Houcheng Jiang, Kun Wang, Yunshan Ma, Shi Jie, Xiang Wang, Xiangnan He, and Tat-seng Chua, ICLR 2025, [arXiv:2410.02355v4](https://arxiv.org/abs/2410.02355v4). The official `figures/intro_part2.pdf` is distributed in the [arXiv source archive](https://arxiv.org/src/2410.02355v4) under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).

The reference PDF, its digitized vector artwork in `scene.json`, `preview.png`, `comparison.png`, and generated artwork reconstructions retain that CC BY 4.0 attribution. They are not relicensed under the repository's MIT code license. FigureFlow's changes are programmatic vector/glyph reconstruction, data binding, source auditing and comparison rendering; the original authors do not endorse or participate in this implementation. Preserve the author/title/source/license and modification notice when redistributing these artworks. The case's `SOURCES.md` and `source_audit.json` record exact versions, checksums and the published figure/table discrepancies.

Glyph paths in the digitized scene reproduce already-typeset artwork; they do not contain a reusable font program or grant rights to font software. The source PDF is retained as the officially published reference, not offered as a font distribution. FigureFlow's independently written extraction, rendering and analysis code is MIT, subject to the separately licensed dependencies used to run it.

## CVPR 2026 video Figure 1 pair

The CVPR 2026 video Figure 1 pair ships recipes and verification code, not the
authors' paper PDFs, embedded fonts, figures or video frames. Rendered local
comparison sheets contain published portions of [Edit-by-Track](https://openaccess.thecvf.com/content/CVPR2026/html/Lee_Generative_Video_Motion_Editing_with_3D_Point_Tracks_CVPR_2026_paper.html)
and [RAPID](https://openaccess.thecvf.com/content/CVPR2026/papers/Lin_RAPID_Reusing_Attention_Sparsity_with_Inter-step_Adaptation_for_Efficient_Video_CVPR_2026_paper.pdf).
Attribution and source manifests travel with those outputs; the MIT code
license does not apply to third-party pixels, typefaces, or derived artwork.

## Online services

Use of the OpenAI API and generated output is also governed by the applicable OpenAI terms and policies. The MIT License for this repository does not grant API access, model weights, service credits, or rights beyond those terms.
