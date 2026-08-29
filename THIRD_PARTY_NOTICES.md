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

## Online services

Use of the OpenAI API and generated output is also governed by the applicable OpenAI terms and policies. The MIT License for this repository does not grant API access, model weights, service credits, or rights beyond those terms.
