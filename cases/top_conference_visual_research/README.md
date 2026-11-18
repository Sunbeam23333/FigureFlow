# Top-conference visual research registry

This case records a source-grounded visual study of representative **Best Paper,
Outstanding Paper, and official honorable-mention** figures from CVPR, ICML,
NeurIPS, and ICLR. It is a design reference for FigureFlow, not a collection of
paper screenshots. We keep official paper/award links, figure-level observations,
derived design tokens, and small native-vector templates; we do **not** vendor
third-party figure images or reuse their experimental values.

## What is retained

| File | Purpose |
|---|---|
| [`catalog.json`](catalog.json) | Machine-readable paper/figure inventory and visual encodings |
| [`palette_tokens.json`](palette_tokens.json) | White-paper, emerald, action, score, and colorblind-safe tokens |
| [`derived_rules.md`](derived_rules.md) | Cross-paper layout rules for main figures, qualitative panels, and data plots |
| [`source_links.md`](source_links.md) | Official awards, proceedings, open-access PDFs, and access date |
| [`../../skill/design-research-figures/assets/tikz/conference_overview_template.tex`](../../skill/design-research-figures/assets/tikz/conference_overview_template.tex) | Editable generic input → representation → evidence overview |

The registry deliberately separates `source_evidence` from `derived_rule`.
Statements about a published figure are observations from the cited official
PDF/HTML; FigureFlow recommendations are marked as derived and should be
validated against the target paper before use.

## Reusable routes

* `hero_evidence`: real input or frame strip → compact representation → output evidence.
* `action_rollout`: timestamp-aligned frames with an action/time rail, goal, and score.
* `qualitative_matrix`: fixed rows for scenes/tasks and fixed columns for methods or stages.
* `multiscale_ladder`: coarse-to-fine grids or repeated stages with one `×L` block.
* `quality_cost_bubble`: quality vs. runtime/compute with log axes, size = parameters,
  and an explicit Pareto or lower-bound reference.
* `small_multiples`: shared axes and one legend for training dynamics, ablations, or scaling laws.
* `text_evidence_score`: a qualitative example directly paired with its statistic or test score.

The existing AlphaEdit, WeLM-Image, and CONCORD-Rec cases remain the executable
examples for data reproduction, green radial charts, and semantic mechanism
diagrams. This registry adds the conference-level design evidence without
pretending that a style observation is a measured result.

## Reproducing the local template

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

## Scope and attribution

The source links are included for scholarship and provenance. Read each paper's
license and conference terms before redistributing any source asset. The
registry contains derived descriptions and FigureFlow-native templates only;
it is not affiliated with CVPR, ICML, NeurIPS, ICLR, or the paper authors.
