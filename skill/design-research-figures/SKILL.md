---
name: design-research-figures
description: Create or revise evidence-grounded, editable technical visuals for research papers, patents, reports, and SOPs—including workflow/framework diagrams, data plots, mechanism diagrams, transfer graphs, qualitative panels, and LaTeX tables. Use when semantic correctness, precise text/connectors, provenance, and vector delivery matter. Do not use for exploratory dashboards, prose-only editing, or decorative slide design.
---

# Design Research Figures / FigureFlow

Build the visual argument, not a decorative diagram. Keep claims, evidence status, data, geometry, typography, raster assets, and captions independently editable. For business workflows, SOPs, and patent overviews, use the same evidence discipline but prefer the safe `FigurePlan` contract and deterministic workflow renderer.

For a complex paper main figure, do not force the task into the repository's 3–6-stage web demo. Use the stateful research harness described in `docs/research-harness.md` at the repository root: explicit complete extracted source text, PDF page inspection, open declarative scenes, actual-font geometry checks, and iterative same-model visual review. Its public task prompt is `prompts/research_harness.md`. This is a task-specific workflow, not a claim to replicate a platform's internal system prompt. The research UI is experimental and opt-in; its explicit upload consent allows supplied source/asset/style pixels to enter model context. The legacy Commons workflow below remains local-only for imported pixels. Do not imply those two privacy boundaries are identical.

For a narrow edit to an approved figure, preserve its scene, assets and stable element IDs. Use the repository's `demo_core.scene_editor` or research `patch_scene` with a base hash and editable-ID scope; inspect the updated render, symbol registry and unchanged-object receipt. See repository `docs/layered-svg-editing.md`. Never rerun whole-image generation just to replace one label or official mark. Read the official-brand and SVG handling rules in [references/assets-and-prompts.md](references/assets-and-prompts.md) before importing or replacing assets.

## Non-negotiable rules

1. Read the relevant paper passage, code path, config, data, and logs before drawing factual content.
2. Write one sentence stating what the reader should conclude from the visual.
3. Assign exactly one primary evidence status: `measured`, `implemented`, `simulation`, `forecast`, `illustrative`, `synthetic-demo`, or `failed-gate`.
4. Show every non-measured status in the figure or table and in its provenance manifest.
5. Never use ImageGen for labels, formulas, plots, precise hardware topology, CUDA timing, or claimed experimental output.
6. Typeset labels and formulas in deterministic vector layers. Compile formulas with a math engine; do not expose raw LaTeX as ordinary SVG text.
7. Inspect the final paper-page render at its actual include width. A beautiful standalone PNG is not proof of readable paper layout.

Read [references/workflow.md](references/workflow.md) before authoring a new figure. For a full paper section or caption, also read [references/paper-writing.md](references/paper-writing.md).

## Route to the right module

Choose the renderer only after the claim and evidence status are fixed.

| Need | Module | Editable source | Renderer |
|---|---|---|---|
| Multi-panel measurements or forecasts | quantitative data figure | YAML + CSV | `render_data_figure.py` |
| Radar audit plus GPU strong scaling | advanced audit figure | YAML or CSV | `render_audit_figure.py` |
| Paper-level framework or method overview | semantic overview | YAML + SVG | `render_overview.py` |
| Report, SOP, or patent workflow | Chinese-friendly workflow | validated JSON + optional PNG alpha | `render_workflow.py` |
| Transfer, dependency, or explicit non-transfer | link graph | YAML | `render_link_graph.py` |
| Exact comparison values and status-aware cells | result table | YAML + TeX fragment | `render_table.py` |
| CUDA lanes, GPU blocks, memory, hardware projection | mechanism diagram | TikZ/LaTeX | `assets/tikz/` + `compile_figures.py` |
| Real rollout or qualitative evidence | case panel | source frames + manifest | `extract_frames.py` plus deterministic composition |
| Missing semantic bitmap | text-free asset only | prompt + PNG alpha | use the `imagegen` skill |

Read [references/module-router.md](references/module-router.md) for the YAML contracts and module-specific checks. Read [references/style-system.md](references/style-system.md) when adapting the theme, typography, or final size.

For a workflow intended for slides, select the allowlisted `presentation-spacious` layout preset rather than inventing font-size floats. For GPU systems visuals, `gpu-green-tech` is available as a generic accelerator-systems palette only: do not use a third-party logo or imply endorsement or affiliation.

## Authoring workflow

### 1. Establish the evidence contract

Record:

- figure claim and reading order;
- inputs, transformations, outputs, controls, and invariants;
- source artifact for each factual stage, edge, formula, and number;
- evidence status and any mixed-status exceptions;
- final target width: single column, double column, or full page;
- caption boundary: what the visual does **not** establish.

Resolve conflicts in this order: runnable implementation and measured traces, current paper text, experiment registry/config, design notes, then explicitly labeled assumptions. Report mismatches instead of silently selecting one.

### 2. Select a visual grammar

Use semantic structure rather than copying the last successful layout. Read [references/layouts-and-shapes.md](references/layouts-and-shapes.md).

For an open-ended main-figure request, create at least six rough candidates spanning three layout families and two density levels. Stable IDs such as `B2`, `R2`, and `Z1` must map to editable sources. This candidate requirement does not apply to a standard data plot, table, arrow repair, or narrowly specified revision.

### 3. Design components by meaning

- Use unique semantic icons; do not reuse a film reel for camera control, T2V, action rollout, and generated video.
- Use film strips only for actual frame sequences.
- Use a zoom or projection connector when a simplified GPU block maps to sourced hardware architecture.
- Encode data, control, synchronization, projection, and unsupported transfer with redundant line styles, markers, or captions—not color alone.
- Remove an icon if it does not improve recognition at final paper width.

### 4. Handle raster assets and real cases

Use sources in this order: actual project output, attributed public benchmark sample, user-provided image, disclosed generated illustration, then vector placeholder. Preserve uncropped originals and provenance.

Before generating a visual reference, search or attach source metadata. In the repository-level FigureFlow app, use `offline-example`, `user-url`, or `wikimedia-commons` through `demo_core.reference_search`. Keep the default offline. The user-URL provider records links without fetching them. The Commons provider calls only its fixed MediaWiki endpoint; bind import to the exact previewed result ID rather than running a second search. An explicitly selected result may then cross `demo_core.reference_import`, which allows only the Commons media host, refuses redirects, enforces byte/pixel/format limits, checks source/author/open-license metadata, strips embedded metadata, and saves a normalized PNG plus provenance inside the run directory. The workflow renderer reads only that local file and never fetches a model- or user-provided URL. Do not send imported reference pixels to the planning or image-generation model. When a real reference enters the canvas, automatically render its title, creator/attribution, license, source platform, and modification notice into every SVG/PDF/PNG; keep full URLs in SVG metadata and the manifest.

For a locally imported image with a nearly uniform border, the asset pipeline may apply its conservative local soft matte. Preserve a complex photographic background when that gate does not pass; never label this fallback as successful semantic segmentation. The `user-url` provider remains record-only to avoid turning the app into an SSRF or signed-URL proxy.

When ImageGen is necessary, invoke the `imagegen` skill and generate text-free components separately. Record the prompt, date, source type, crop, and whether the asset is illustrative. Read [references/assets-and-prompts.md](references/assets-and-prompts.md).

For chroma-keyed icons, use `scripts/remove_chroma.py` to create a soft alpha matte and remove colored edge spill before composition.

### 5. Render with absolute skill paths

Resolve the skill root from the loaded `SKILL.md` location. Do not assume the user's current directory contains `scripts/`, and use `python3` on this workstation.

Runtime requirements are Python 3 with NumPy, Pandas, Matplotlib, PyYAML, Pillow, and CairoSVG; XeLaTeX compiles tables/TikZ/demo pages; Poppler supplies `pdftoppm`, `pdfinfo`, and `pdffonts`. Check these before a large candidate build.

```bash
FIGURE_SKILL_ROOT="/absolute/path/to/design-research-figures"

python3 "$FIGURE_SKILL_ROOT/scripts/render_overview.py" overview.yaml --output-dir output
python3 "$FIGURE_SKILL_ROOT/scripts/render_data_figure.py" data_figure.yaml --output-dir output
python3 "$FIGURE_SKILL_ROOT/scripts/render_audit_figure.py" advanced_audit.yaml --output-dir output
python3 "$FIGURE_SKILL_ROOT/scripts/render_link_graph.py" link_graph.yaml --output-dir output
python3 "$FIGURE_SKILL_ROOT/scripts/render_table.py" table.yaml --output-dir output
python3 "$FIGURE_SKILL_ROOT/scripts/render_workflow.py" figure_plan.json --asset-dir processed_icons --output-dir output
```

For TikZ candidates and rollout strips:

```bash
python3 "$FIGURE_SKILL_ROOT/scripts/compile_figures.py" figures/candidates --output-dir figures/rendered
python3 "$FIGURE_SKILL_ROOT/scripts/extract_frames.py" rollout_strip.png --count 5 --output-dir rollout_frames
python3 "$FIGURE_SKILL_ROOT/scripts/make_gallery.py" figures/rendered --output figures/gallery.png
```

### 6. Write the caption as an evidence contract

A useful caption contains, in order:

1. the takeaway;
2. what each panel, mark, edge, or shade encodes;
3. units, uncertainty, aggregation, seed count, and evidence status;
4. the decision rule or falsification gate;
5. the interpretation boundary.

For tables, separate published, measured, forecast, and invalid-comparison rows or cells. Prefer `booktabs`, `tabularx`, and explicit column widths over indiscriminate `\resizebox`.

### 7. Compile and verify

Every primary visual must include:

- editable source;
- one-page vector PDF;
- 240 DPI review PNG;
- source CSV or frame manifest when applicable;
- provenance/status manifest;
- final paper-page screenshot.

Run structural checks, then inspect the rendered pixels:

```bash
python3 "$FIGURE_SKILL_ROOT/scripts/audit_figure.py" output --margin 16 --json
python3 "$FIGURE_SKILL_ROOT/scripts/qa_pdf.py" output/figure.pdf output/table.pdf --single-page --log output/compile.log --json
python3 "$FIGURE_SKILL_ROOT/scripts/qa_pdf.py" output/paper.pdf --expect-pages 3 --log output/paper.log --json
```

Before publishing a repository or delivery ZIP, run the public-release gate. Pass ignored delivery artifacts explicitly; the default repository inventory covers tracked and non-ignored files.

```bash
python3 "$FIGURE_SKILL_ROOT/scripts/check_public_release.py" --root /path/to/repository --artifact output/delivery.zip
```

The gate rejects credentials, custom API endpoints, local machine paths, unsafe ZIP members, and non-empty provider response IDs in manifests. It reports locations and rule names without echoing matched values.

Reject clipping, node/label overlap, arrows through text, stale page renders, accidental second pages, Type 3 or unembedded fonts, `Overfull` boxes, unexplained encodings, and text below the target readable size. Re-render final pages from the current PDF rather than reusing old contact sheets. Read [references/qa.md](references/qa.md).

## Complete demo

Build the self-contained demo to verify the entire module suite:

```bash
FIGURE_SKILL_ROOT="/absolute/path/to/design-research-figures"
python3 "$FIGURE_SKILL_ROOT/scripts/build_visual_demo.py" --output-dir "$FIGURE_SKILL_ROOT/demo/output"
```

The demo produces a five-stage overview, a four-panel quantitative figure with source CSVs, an explicit non-transfer graph, a LaTeX result table, a compiled two-column paper, page renders, a gallery, and a provenance manifest. All demo numbers are synthetic and visibly labeled.

The repository-level FigureFlow app adds GPT-5.6-sol structured planning, three constrained workflow layouts, semantic-icon chroma processing, Chinese vector typesetting, stage timings, and downloadable manifests. Its offline mode is a disclosed preset replay, never a simulated online response. Do not report a team efficiency percentage until the same tasks have been timed against manual document drawing and whole-image generation plus editing.

## Resource map

- [references/workflow.md](references/workflow.md): evidence extraction and provenance
- [references/module-router.md](references/module-router.md): renderer selection and YAML contracts
- [references/paper-writing.md](references/paper-writing.md): paper narrative, formulas, captions, and negative results
- [references/style-system.md](references/style-system.md): palette, typography, sizing, and visual encodings
- [references/layouts-and-shapes.md](references/layouts-and-shapes.md): candidate layout and shape library
- [references/assets-and-prompts.md](references/assets-and-prompts.md): real cases, ImageGen, crops, and provenance
- [references/qa.md](references/qa.md): semantic, geometric, PDF, and paper-page QA
- `assets/themes/academic_audit.json`: shared Python/SVG/LaTeX design tokens
- `assets/themes/gpu_green_tech.json`: generic GPU-systems workflow tokens; no third-party logo or endorsement
- `assets/tikz/`: GPU Green, Emerald, Warm Editorial, and mechanism templates
- `demo/source/`: working YAML examples for every deterministic module
- `demo/README.md`: rebuild instructions and the expected gallery filename (generated locally, not committed)
