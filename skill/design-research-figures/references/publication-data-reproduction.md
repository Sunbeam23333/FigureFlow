# Published-figure reconstruction and data-driven charts

Use this route when the user asks to reproduce a published data figure closely, analyze its reported numbers, or plot replaceable tabular data in the same visual family. AlphaEdit Figure 2 is the bundled working case. Read only this reference and the case's `SOURCES.md`/`PROMPTS.md` for that task; the main-figure candidate workflow is unnecessary for a specified reproduction.

## Choose the mode before authoring

| Request | Route | Meaning |
|---|---|---|
| Reproduce AlphaEdit Figure 2's artwork | `--case alphaedit-figure2` | Faithful reconstruction of a digitized official vector figure |
| Replace values or methods; analyze reported data | `--csv ... --kind annular` | Recompute grouped annular bars from the supplied values |
| Inspect precise comparisons, signed values, or long labels | `--csv ... --kind small-multiples` | Plot original values on independent panel axes |

Faithful AlphaEdit mode reassembles 71 paths and 555 glyph instances extracted from the official Illustrator-exported PDF. Its 55 CSV labels are independently checked against white numeric spans in the source PDF and bound glyphs. This is FigureFlow's source-artwork reconstruction, not the authors' original plotting code, and its fixed bar geometry is not calculated from the CSV. A changed CSV belongs in the data-driven route; do not relabel fixed bars with new data.

The official figure is the visual source of truth for faithful mode. Compare its numbers with the paper's tables and record conflicts separately. AlphaEdit has four substantive Figure 2 / Table 1 conflicts documented in `cases/alphaedit_figure2/SOURCES.md`; preserve the source figure's labels for reproduction. Never interpret this pipeline as rerunning the model experiments.

## Resolve the runtime

`scripts/render_publication_data.py` is a wrapper around the FigureFlow repository's `demo_core.alphaedit_reproduction` and `demo_core.data_analysis` modules. An installed skill needs a FigureFlow checkout; supply its actual root explicitly. Do not claim this new module is self-contained in the installed skill folder.

From the FigureFlow repository root, install:

```bash
python3 -m pip install -r requirements-reproduction.txt
```

Cairo and Poppler are system dependencies for the faithful PDF/export/comparison path. Typical macOS installation is `brew install cairo poppler`; Linux packages include `libcairo2` and `poppler-utils`. PyMuPDF is optional and only needed to regenerate the digitized case or use its alternative rasterizer. It has AGPL/commercial dual licensing; ordinary replay uses the committed scene and Poppler.

Resolve `FIGURE_SKILL_ROOT` from the loaded `SKILL.md`, and use explicit paths:

```bash
python3 "$FIGURE_SKILL_ROOT/scripts/render_publication_data.py" \
  --figureflow-root /path/to/FigureFlow --case alphaedit-figure2 \
  --output-dir /path/to/output/alphaedit_reproduction

python3 "$FIGURE_SKILL_ROOT/scripts/render_publication_data.py" \
  --figureflow-root /path/to/FigureFlow --csv /path/to/data.csv \
  --kind annular --title "Model comparison" --focus-method "Candidate" \
  --output-dir /path/to/output/data
```

The direct repository CLI also accepts per-metric optimization directions:

```bash
python3 -m demo_core.data_analysis data.csv --chart small-multiples \
  --title "Model comparison" --focus-method "Candidate" \
  --lower-is-better "Latency (ms)" --output-dir output/data
```

`--lower-is-better` is a direct module option, not a wrapper option. Each occurrence names one metric. Check `--help` when adapting a command to a different checkout.

## Long-table contract and evidence

```csv
metric,method,value,label,source,evidence_status
Accuracy,Baseline,0.85,0.85,results.csv,user-supplied
Accuracy,Candidate,0.90,0.90,results.csv,user-supplied
Latency (ms),Baseline,12,12,results.csv,user-supplied
Latency (ms),Candidate,10,10,results.csv,user-supplied
```

Required fields: `metric,method,value`. Optional fields: `label,source,evidence_status`. Preserve numeric display strings such as `5.90` and `0.90`; `label` must parse to the same value. Maintain complete metric × method coverage, finite numbers, and one row per pair. The loader rejects gaps and duplicate pairs rather than imputing observations. An absent source defaults to the input filename; an absent status defaults to `user-supplied`.

The new data module accepts `published-figure`, `published-table`, `user-supplied`, `remeasured`, `measured`, `synthetic-demo`, `simulation`, `forecast`, and `failed-gate`. These are **this module's** evidence codes; they do not expand the legacy `FigurePlan` or older YAML renderer enum. `remeasured` is a declaration by the data provider, not something FigureFlow proves or performs. Mixed statuses remain attached to individual observations and are exposed in labels and manifests.

Use the supplied data's actual origin. Digitizing a published chart is `published-figure`, not `measured`; copying a paper table is `published-table`. Neither permits inference of unreported precision, seeds, error bars, or statistical significance.

## Data-driven geometry and analysis

- Annular bars support 2–24 metrics, 1–12 methods, at most 120 bars, nonnegative values, and metric names of at most 32 characters. Switch to small multiples when those limits or readability make the ring unsuitable.
- Each annular metric is scaled to its own maximum. Zero is a baseline tick with zero radial length. The figure and manifest disclose this transform. Equal bar lengths across different metrics do not mean equal performance or effect size.
- Small multiples support signed values and keep original units with independent panel axes. They support up to 36 metrics and 20 methods; split larger inputs.
- Analysis compares methods separately within each metric, respects higher/lower-is-better, preserves ties, and reports the focus method's difference from the best alternative. Relative advantage is undefined when that alternative is zero. No cross-metric mean or significance claim is calculated.

Return the CSV, analysis JSON/Markdown, source/status/hash manifest, and vector/PNG outputs together. Explain the important comparisons with units and the source's precision; do not present visualization as an experimental rerun.

## Faithful QA, delivery, and licensing

Preserve original tiny labels and weak contrast when exact artwork reproduction is requested, and document those inherited defects. Do not silently improve the reference or add a conspicuous evidence watermark to its canvas. Put status and attribution in an adjacent caption, SVG/PDF metadata, attached source/data files, and provenance records. For a new data-driven figure, use the renderer's visible evidence and scaling notes.

Compare the official reference and reconstruction at the same CropBox, DPI, and rasterizer, without fitting, padding, or aligning one to inflate agreement. Inspect the difference image and foreground error as well as overall pixel agreement; a mostly white canvas can produce a high match percentage. Report actual metrics from `report.json`, acknowledge residual glyph-outline/antialiasing differences, and do not call a nonzero-error reconstruction pixel-identical.

The faithful run writes SVG/PDF/PNG, reference/comparison images, the 55-row data, scene, source audit, prompts, report and manifest. Its `reproduction.zip` includes a minimal runnable `replay/` directory and `REPLAY.txt`. The normal run is offline and requires no API key. Public task prompts and reproducible commands belong in the case; do not claim to export platform-hidden prompts or private reasoning.

Keep the official AlphaEdit PDF, digitized scene, and artwork-derived previews under their CC BY 4.0 attribution. FigureFlow implementation code remains MIT; do not apply that code license to the source artwork. Glyph paths reproduce already-typeset art and do not distribute a reusable font program or grant font rights. See the case `SOURCES.md` and repository `THIRD_PARTY_NOTICES.md` before packaging.
