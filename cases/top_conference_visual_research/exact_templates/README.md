# Exact-paper TikZ templates

This directory contains the paper-faithful, editable vector layer for the 12 requested visual patterns. Each template is a standalone `main.tex` and is allowlisted by `manifest.json`.

These are derived vector reconstructions of the published figure grammar—not vendored screenshots or claims of pixel identity. The manifest records the official source PDF, page, figure ID, panel order, semantic colors, and the fidelity boundary. No paper image, screenshot, or external raster asset is stored in this directory.

The templates intentionally do **not** reuse `conference_overview_template.tex`; that file remains a generic grammar demo and is not an exact-paper route.

## FigureFlow route

```bash
python3 skill/design-research-figures/scripts/render_exact_template.py --list
python3 skill/design-research-figures/scripts/render_exact_template.py \
  --template d4rt_fig1 --output-dir rendered/exact --dpi 220
```

The renderer accepts only IDs in `manifest.json`, compiles the selected TikZ source with XeLaTeX, renders a review PNG, audits the PDF, and writes a manifest containing source hash, compiler metadata, output hashes, and QA results. It never downloads a paper or embeds a paper image during rendering.

## Template map

| ID | Native layout grammar |
|---|---|
| `d4rt_fig1` | video strip → encoder → fixed global scene → decoder/query heads → task outputs |
| `ovoxel_fig1` | native 3D → sparse structured voxel latent → geometry/appearance streams |
| `nitrogen_fig1` | gameplay harness / vision–action agent / video-action data hub |
| `gated_attention_fig1` | gate-placement mechanism + PPL/MMLU bars + 3T-token loss |
| `artificial_hivemind_fig1` | model legend + dense PCA response cloud + direct facet annotations |
| `superposition_fig1` | 2×2 hidden-space concept and log–log scaling panels |
| `met3r_fig5` | method-by-frame qualitative grid + FID/MET3R evidence + temporal curve |
| `see3d_fig2` | curation → time-dependent visual condition → MVD model |
| `mixture_of_scores_fig1` | disparity histograms + radar summaries + quality–cost evidence |
| `phase_transition_fig1` | log model-size threshold plot + two mixing-ratio small multiples |
| `scaling_extrapolation_fig1` | loss-vs-FLOPs + observed/extrapolated optimal-mixture ribbon |
| `uncertainty_swarm_fig1` | KDE density + ordered CI swarm + specification annotation |

All labels, formulas, axes, legend anchors, markers, and colors are native TikZ/PGFPlots tokens and can be changed without touching a raster layer.
