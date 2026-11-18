# CONCORD-Rec Figure 1/2 reference case

This case preserves the user-approved CONCORD-Rec visual grammar and the two
editable renderers used for the paper's first two figures. It is a style and
source-code reference for FigureFlow, not a claim that FigureFlow reran the
paper's training or reproduced its benchmark results.

## Entry points

| Figure | Source | Role | Primary status |
|---|---|---|---|
| Figure 1 / overview | `sources/figure1_style_refinement_revise.py` (`CO-F-original`) | observed history → behavior backbone + modality paths → tokenwise allocation → feasible catalog → detached utility supervision | `illustrative` presentation layer over an implemented topology |
| Figure 2 / network | `sources/figure2_network_render_v4.py` | three semantic rails: behavioral denoiser, modality conditioning, offline utility supervision, plus the bottom fusion/output rail | `illustrative` architecture specification |

The `reference/` directory contains the approved vector PDF/SVG and review PNG
for both figures. `architecture_base_v8.*` is the earlier deterministic base
render produced by `figure1_architecture_render_v8.py`; `architecture.*` is the
approved later CO-F-original style refinement. `assets/network_semantic_assets.png` is retained only as a
text-free illustrative icon sheet; all labels, equations, connectors, masks,
and panel geometry remain deterministic vector code.

## Reuse recipe

1. Read `SOURCES.md` and `provenance.json` before adapting a panel.
2. Keep the role mapping: navy = inherited behavioral backbone, teal = learned
   conditioning/fusion, violet = observed modality context, amber = detached
   offline supervision.
3. Keep shape semantics: stacked cards/tensor sheets = repeated or shared
   states; trapezoids = projection; hexagons = fusion/loss operations;
   cylinders = catalog/posterior stores; dashed arrows = detached supervision.
4. Replace paper-specific labels and formulas only in native text/LaTeX layers.
   Do not use ImageGen to draw text, plots, hardware topology, or equations.
5. Re-render at final paper width and run `audit_figure.py` and `qa_pdf.py`.

The sources are intentionally archived verbatim so a future revision can diff
against the approved paper implementation. Their original absolute paths are
kept only in the local provenance record, never in a public FigureFlow plan.

To re-render the archived base/network sources with the bundled local dependencies:

```bash
python3 cases/concord_rec_reference/render_reference.py
```

The adapter does not alter the archived source files; it stages their relative
assets and updates `architecture_base_v8.*` plus `network_structure.*`. The
approved `architecture.*` remains the retained CO-F-original output; the final
style-refinement script is archived verbatim for future diffs because it also
depends on the upstream approved SVG and review candidate.
