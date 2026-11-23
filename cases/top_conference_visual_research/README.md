# Top-conference visual research registry

This case records a source-grounded visual study of representative **Best Paper,
Outstanding Paper, and official honorable-mention** figures from CVPR, ICCV,
ICML, NeurIPS, and ICLR. It is a design reference for FigureFlow, not a collection of
paper screenshots. We keep official paper/award links, figure-level observations,
derived design tokens, and small native-vector templates; we do **not** vendor
third-party figure images or reuse their experimental values.

## What is retained

| File | Purpose |
|---|---|
| [`catalog.json`](catalog.json) | Machine-readable paper/figure inventory and visual encodings |
| [`palette_tokens.json`](palette_tokens.json) | White-paper, emerald, action, score, and colorblind-safe tokens |
| [`derived_rules.md`](derived_rules.md) | Cross-paper layout rules for main figures, qualitative panels, and data plots |
| [`research_digest_20261124.md`](research_digest_20261124.md) | New official-source survey of world-model main figures and data-chart grammars |
| [`source_links.md`](source_links.md) | Official awards, proceedings, open-access PDFs, and access date |
| [`exact_templates/`](exact_templates/) | Thirteen allowlisted, paper-faithful TikZ/PGFPlots templates with per-figure provenance |
| [`exact_templates/manifest.json`](exact_templates/manifest.json) | Figure IDs, official source pages, panel grammar, and semantic palettes |
| [`exact_templates/replication_registry.json`](exact_templates/replication_registry.json) | Validated source/page/crop/grammar/palette/evidence/QA contract for every exact template |
| [`figureflow_exact_reproduction_atlas.pdf`](figureflow_exact_reproduction_atlas.pdf) | Exact-template contact-sheet PDF used for visual QA |
| [`build_exact_reproduction_atlas.py`](build_exact_reproduction_atlas.py) | Rebuilds the contact-sheet PDF from the native templates |
| [`figureflow_source_locked_atlas.pdf`](figureflow_source_locked_atlas.pdf) | Pixel-faithful crops from the cited published PDFs |
| [`build_source_locked_atlas.py`](build_source_locked_atlas.py) | Rebuilds the source-locked atlas when the 12 cited PDFs are supplied locally |
| [`figureflow_top_conference_atlas.pdf`](figureflow_top_conference_atlas.pdf) | Legacy eight-page style survey; not an exact-paper reproduction route |
| [`../../skill/design-research-figures/assets/tikz/conference_overview_template.tex`](../../skill/design-research-figures/assets/tikz/conference_overview_template.tex) | Legacy generic input → representation → evidence grammar demo |

The registry deliberately separates `source_evidence` from `derived_rule`.
Statements about a published figure are observations from the cited official
PDF/HTML; FigureFlow recommendations are marked as derived and should be
validated against the target paper before use.

The source-grounded exact-template registry is validated independently:

```bash
python3 skill/design-research-figures/scripts/validate_mainfigure_registry.py
```

It records source URL, page, normalized crop, reading order, palette,
typography, evidence boundary, and 540 pt paper-width QA for every allowlisted
template. The newly added `nwm_fig1` entry covers Navigation World Models
Figure 1; supply the official PDF locally to render its pixel-faithful crop.

The exact-template registry adds a stricter replication contract: every entry
has an HTTPS source URL, source page, normalized crop, explicit fidelity
boundary, renderer route, reading order, palette, typography note, evidence
status, and 540 pt paper-width QA gate. Validate it before adding a new paper:

```bash
python3 skill/design-research-figures/scripts/validate_mainfigure_registry.py
```

The contract stores no paper screenshots or experimental data. A source-locked
crop is used only as a local QA reference when the cited PDF is supplied; the
native TikZ/Pgfplots source remains the editable reproduction artifact.

## Reusable routes

* `hero_evidence`: real input or frame strip → compact representation → output evidence.
* `action_rollout`: timestamp-aligned frames with an action/time rail, goal, and score.
* `qualitative_matrix`: fixed rows for scenes/tasks and fixed columns for methods or stages.
* `multiscale_ladder`: coarse-to-fine grids or repeated stages with one `×L` block.
* `quality_cost_bubble`: quality vs. runtime/compute with log axes, size = parameters,
  and an explicit Pareto or lower-bound reference.
* `small_multiples`: shared axes and one legend for training dynamics, ablations, or scaling laws.
* `text_evidence_score`: a qualitative example directly paired with its statistic or test score.

For figures containing real video frames, rendered meshes, or complex artwork,
use `exact_templates/reference_crop_manifest.json` with
`skill/design-research-figures/scripts/render_reference_figure.py`. It takes the
cited PDF as an explicit local input, crops the published figure region, and
records the source hash and crop coordinates without committing the paper PDF.

The existing AlphaEdit, WeLM-Image, and CONCORD-Rec cases remain the executable
examples for data reproduction, green radial charts, and semantic mechanism
diagrams. This registry adds the conference-level design evidence without
pretending that a style observation is a measured result.

## Reproducing the local template

The paper-faithful route is allowlisted and independent of the generic FigurePlan
workflow. List IDs or render one exact template with:

```bash
python3 skill/design-research-figures/scripts/render_exact_template.py --list
python3 skill/design-research-figures/scripts/render_exact_template.py \
  --template met3r_fig5 --output-dir /tmp/figureflow_exact --dpi 220
```

This creates editable-source provenance next to a one-page PDF and review PNG.
The output manifest records the source hash, compiler, output hashes, and the
explicit `layout-faithful / not pixel-identical` boundary.

From the FigureFlow checkout:

```bash
python3 skill/design-research-figures/scripts/compile_figures.py \
  skill/design-research-figures/assets/tikz/conference_overview_template.tex \
  --output-dir /tmp/figureflow_conference_template
python3 skill/design-research-figures/scripts/audit_figure.py \
  /tmp/figureflow_conference_template/conference_overview_template.pdf \
  --margin 12 --json
python3 skill/design-research-figures/scripts/qa_pdf.py \
  /tmp/figureflow_conference_template/conference_overview_template.pdf \
  --single-page --json
```

For data charts, `render_data_figure.py` now supports line confidence bands,
point error bars, direct end labels, and `kind: bubble` with a numeric
`size_field`. Error bars/bands are only valid when the source CSV contains real
seed or interval evidence; the figure status must still be declared in YAML.

## PDF atlas

The checked-in `figureflow_top_conference_atlas.pdf` is a visual handoff for
the current integration. It has eight landscape A4 pages: grammar families,
CONCORD-Rec native examples, AlphaEdit/data-chart examples, the white-paper
overview template, a world-model rollout rail, palette tokens, and provenance /
QA. Rebuild it with an environment that has ReportLab, Pillow, and pypdf:

```bash
python3 build_atlas.py --output figureflow_top_conference_atlas.pdf
```

## Scope and attribution

The source links are included for scholarship and provenance. Read each paper's
license and conference terms before redistributing any source asset. The
registry contains derived descriptions and FigureFlow-native templates only;
it is not affiliated with CVPR, ICML, NeurIPS, ICLR, or the paper authors.
