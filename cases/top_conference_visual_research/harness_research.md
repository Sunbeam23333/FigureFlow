# Academic figure harnesses worth studying

This is a source-grounded review of public figure-generation and composition
systems. The goal is not to replace FigureFlow with an image generator; it is
to identify workflow ideas that improve case-study composition, style matching,
editable output, and QA.

## Shortlist

| Project | Link | What its output/pipeline is good at | Adopt in FigureFlow? |
|---|---|---|---|
| PaperBanana / PaperVizAgent | [Google Research paper page](https://research.google/pubs/paperbanana-automating-academic-illustration-for-ai-scientists/) · [community implementation](https://github.com/llmsresearch/paperbanana) | Retriever → planner → stylist → visualizer/critic; reference-conditioned diagrams, batch manifests, composite panels, plot mode, full-paper orchestration, and evaluation. It explicitly switches numerical plots to executable plotting code. | **Yes, as orchestration only.** Adopt the planner/critic state machine, reference-set style guide, batch manifest, composite assembly, and run reports. Keep FigureFlow's deterministic TikZ/Matplotlib renderers as executors. |
| Crafter / CraftEditor | [paper](https://arxiv.org/abs/2605.30611) · [code](https://github.com/HaozheZhao/Crafter) | A four-role loop with diversity-driven plan exploration, structured corrective edits, directive visual critics, and raster-to-editable-SVG conversion. The paper describes a shared evolving specification rather than free-form prompt accumulation. | **Yes, strongly.** Add typed revision operations, preserve lists, bbox-based visual review, and a bounded refinement loop. Do not use its raster executor for formulas or exact plots. |
| FigMirror | [GitHub](https://github.com/VILA-Lab/FigMirror) · [paper/results](https://arxiv.org/abs/2608.30241) | Reference figure + target data → Drawer/Reviewer loop; style transfer to an editable Matplotlib script and camera-ready PDF. It reports a 150-instance PlotTwin-Bench evaluation and exposes a style-mirroring showcase. | **Yes for data charts.** Adopt reference-figure measurement, drawer/reviewer roles, preserve-list state, and reference-vs-candidate comparison. Keep data values and statistical transforms deterministic. |
| Academic Figure Skill | [GitHub](https://github.com/TingxiYu/academic-figure-skill) | Question-driven 8-step workflow, archetype classification, 29 figure types, fixed journal widths, vector PDF + 300 dpi preview, and four-pass QA. | **Yes for routing/QA.** Adopt intent → archetype → style baseline → asset scan → render → QA. Its Nature/Cell/Science defaults should not overwrite our CVPR/NeurIPS palette. |
| paper-toolkit | [GitHub](https://github.com/Yokumii/paper-toolkit) | Deterministic evidence DAG, structured checks, LaTeX composition, page introspection, figure rendering, and paper-analysis pipeline. | **Yes for provenance.** Adopt evidence-DAG IDs, page introspection, and build checks; leave prose/agent policy outside FigureFlow. |
| Make My Figure | [GitHub](https://github.com/surPoudel/make-my-figure) | CSV/Excel → FigureSpec → statistics/annotations → multi-panel layout → vector+raster export, with JSON specs and reusable style/layout presets. | **Yes for data figures.** Adopt the separation of data identity, PlotSpec, StatsSpec, FigureSpec, and layout presets. |
| AutomaTikZ | [GitHub](https://github.com/potamides/AutomaTikZ) · [ICLR paper](https://arxiv.org/abs/2310.00367) | Text-guided TikZ generation with a large TikZ dataset and a vector intermediate representation. | **Partially.** Adopt TikZ as an editable IR and compile/render loop. Do not trust free-form generated coordinates without FigureFlow's bbox/overlap/audit gates. |
| Figura | [GitHub](https://github.com/chrischoy/figura) | Agent skill that renders Python plots and standalone TikZ diagrams to PDF/PNG/SVG, with an explicit render → view → fix loop and reusable semantic styles. | **Yes for developer UX.** Adopt the command contract, stable figure stems, paper-width previews, and render/view/fix loop. |
| OpenTikZ | [GitHub](https://github.com/opentikz/opentikz) · [gallery](https://opentikz.org) | CC0 icon/template library, standalone TikZ files, metadata validation, preview rendering, and a catalog-driven gallery. | **Yes for assets.** Reuse only license-compatible icons and import them through a provenance-aware asset registry. |
| SciencePlots | [GitHub](https://github.com/garrettj403/SciencePlots) | Mature Matplotlib style sheets with journal variants, consistent typography, axes, line widths, and LaTeX export. | **Yes for a baseline preset.** Import spacing/line-width ideas, but keep our semantic palettes and evidence-status rules. |
| Pylustrator | [paper](https://arxiv.org/abs/1910.00279) · [code](https://github.com/rgerkin/pyLustrator) | GUI composition changes are recorded back into the calling Matplotlib script, closing the gap between plot generation and final multi-panel assembly. | **Yes for optional human polish.** Add an exportable composition patch format; do not make GUI state the only source of truth. |

## What their results suggest for our case-study request

The strongest common pattern is not “generate a prettier picture.” It is:

`reference/case evidence → typed plan → deterministic executor → visual critic with bboxes → structured revision → paper-width QA`.

For FigureFlow, the executor should remain split by semantic risk:

- **Real case panels:** deterministic crop/frame extraction and source manifest.
- **Numerical plots:** CSV/JSON + Matplotlib/PGFPlots; no image generation.
- **Framework/mechanism:** TikZ/SVG with explicit coordinates and semantic shape
  types.
- **Text/formulas:** native LaTeX/vector text.
- **Illustrative icons only:** optional image generation, text-free and marked
  illustrative.

This gives us the case-study collages and overlapping insets seen in strong
papers without inheriting the failure mode of a raster-only generator: invented
labels, wrong numerical geometry, and uneditable output.

## Recommended FigureFlow adoption order

1. Add `case-study-in-flow` as a first-class layout family with input/output
   frame strips, overlap/projection links, and a case manifest.
2. Add a typed `FigureSpec`/`RevisionSpec` layer inspired by PaperBanana,
   Crafter, FigMirror, and Make My Figure.
3. Add a Drawer/Reviewer comparison report with reference/candidate bboxes and a
   preserve list. The reviewer should return actionable edits, not a scalar
   aesthetic score.
4. Add paper-width rendering and final-page screenshots to every build.
5. Add a style corpus route that learns spacing, panel ratios, fonts, and palette
   roles from selected CONCORD-Rec/WeLM-Image/top-conference references, while
   keeping all factual labels and metrics source-grounded.
