# Module Router and Source Contracts

## Decide from the claim

| Reader question | Use | Avoid |
|---|---|---|
| What is the paper's end-to-end logic? | semantic overview | dense axes or exact result values |
| How does a report, SOP, or patent process move from input to checked output? | FigureFlow workflow | free-form AI coordinates or whole-image text generation |
| What changed, by how much, and with what uncertainty? | quantitative figure | icon-driven framework art |
| Which entities transfer, depend, or explicitly do not transfer? | link graph | a generic box-and-arrow pipeline |
| What are the exact values and statuses? | result table | encoding every number as a bar |
| How do streams, kernels, memory tiers, or blocks interact? | TikZ/SVG mechanism | AI-generated hardware architecture |
| What did the model actually produce through time? | real case panel | generated illustration presented as output |

Do not combine modules merely to fill space. Combine them only when the paper claim genuinely needs both structure and evidence, such as a mechanism beside a real rollout strip.

## Shared source fields

Every YAML source should identify:

```yaml
title: "One claim-shaped title"
evidence_status: "forecast"
status: "FORECAST - NOT MEASURED"
status_kind: "warning"
output_name: "stable_file_stem"
footer: "Source, seed, or provenance summary"
```

Allowed primary statuses are `measured`, `implemented`, `simulation`, `forecast`, `illustrative`, `synthetic-demo`, and `failed-gate`. The visible status line may be friendlier, but the manifest must preserve the canonical value.

Quote LaTeX carefully in YAML: prefer single-quoted scalar values such as `'Recovery $\uparrow$'`, or double every backslash inside double quotes. A raw `\uparrow`, `\frac`, or `\textbf` in a double-quoted YAML string can be parsed as an escape.

## Quantitative data figure

Use `render_data_figure.py`. The source lists one to four panels, each backed by a CSV. Supported panel forms are standard line/scatter and grouped bar; line series may include `low` and `high` columns for a real interval or seed-derived band.

```yaml
panels:
  - title: "Held-out residual"
    csv: "data/residuals.csv"
    x_label: "log effective rank"
    y_label: "scaling residual"
    series:
      - {label: "held-out", x: "rank", y: "observed", kind: "scatter", color: "blue"}
      - {label: "frozen predictor", x: "rank", y: "fitted", color: "teal"}
    gates:
      - {value: 0, label: "base-law residual = 0", color: "gray", linestyle: "--"}
```

Requirements:

- axes carry units;
- uncertainty states its construction and seed count;
- a single seed never receives a fabricated error band;
- markers and line styles duplicate essential color distinctions;
- forecasts and synthetic data remain marked inside the figure and source CSV.

## Semantic overview

Use `render_overview.py` for three to six stages. It outputs editable SVG plus PDF and PNG. Stage icons are deterministic vector primitives; formulas are rendered to path-only SVG assets before embedding.

```yaml
stages:
  - title: "Evidence ledger"
    subtitle: "paper + code + logs"
    accent: "blue"
    background: "light_blue"
    icon: "data"
    tags: [{label: "claims", color: "blue"}]
    body: ["Seeds and units pinned"]
  - title: "Two decisions"
    blocks:
      - {label: "FORECAST", title: "Held-out residual", formula: "\\widehat L_1=\\widehat L_0+\\delta\\log r", color: "violet"}
      - {label: "ALLOCATE", title: "Compute-optimal capacity", formula: "q_t\\propto(r_t/c_t)^{1/(1+\\rho)}", color: "teal"}
gates:
  - {label: "OOD RMSE improves >=15%", color: "blue", fill: "light_blue"}
```

Keep stage titles short. If one stage branches, use independent source/destination ports and distinct curves; do not stack coincident arrows. The lower gate belt is for preregistered stopping or falsification criteria, not feature marketing.

## Report, SOP, or patent workflow

Use `render_workflow.py` when the deliverable is a Chinese-friendly process figure rather than a paper method overview. Treat the language model as a planner only: it may propose semantic stages and asset prompts, but the renderer owns geometry, connectors, exact text, evidence labels, and file output. Validate the JSON before rendering; never execute model-produced code or accept model-produced file paths.

The standalone `FigurePlan` contract is:

```json
{
  "title": "One claim-shaped title",
  "takeaway": "The single conclusion a reader should retain.",
  "layout_family": "ribbon",
  "layout_preset": "presentation-spacious",
  "theme": "academic-audit",
  "reference_assets": [
    {
      "id": "offline-figureflow-workflow",
      "title": "FigureFlow bundled synthetic workflow example",
      "uri": "example://figureflow/examples/figureflow_workflow.png",
      "source_type": "offline-example",
      "provider": "offline-example",
      "media_type": "image",
      "attribution": "Bundled synthetic-demo reference; no network request was made."
    }
  ],
  "evidence_status": "synthetic-demo",
  "status_label": "合成演示｜未含实测提效",
  "stages": [
    {
      "title": "需求提炼",
      "subtitle": "形成节点与证据链",
      "body": ["提炼 3–6 个节点", "标注证据状态"],
      "accent": "navy",
      "asset_key": "data",
      "asset_prompt": "Text-free semantic icon on a flat chroma background; no labels or watermark.",
      "evidence_status": "synthetic-demo"
    }
  ],
  "gates": ["节点与证据完整", "边界字体通过"],
  "caption": "State what the figure establishes and what it does not.",
  "warnings": ["全部内容均为合成演示"]
}
```

Contract limits:

- provide 3–6 stages with unique titles and unique `asset_key` values;
- choose `ribbon`, `bowtie`, or `dual-rail`; use `ribbon` when the process is simply sequential;
- choose `standard` or `presentation-spacious`; the presentation preset uses approximately 25% larger stage/gate typography and permits at most two body lines per stage;
- choose `academic-audit` or the generic `gpu-green-tech` token theme; the latter uses no third-party logo and must not imply endorsement or affiliation;
- choose assets only from `layout_planner`, `icon_factory`, `chroma_matte`, `vector_typeset`, `qa_export`, `gpu_server`, `robot_inspection`, `data`, `process`, `decision`, `store`, and `output`;
- choose accents only from `navy`, `blue`, `teal`, `orange`, and `violet`;
- keep each body to at most three short lines, gates to five labels, and warnings to six items;
- use one canonical evidence status from the shared list, and do not mark the overall plan `measured` unless every stage is measured;
- keep stage titles within 24 display units, subtitles within 28, body lines within 24, gate labels within 20, and the top status label within 30. CJK characters consume two display units.
- attach at most eight reference assets with unique IDs and portable `example://` or non-credentialed HTTP(S) URIs. Only a caller/provider may attach them; the planner must never invent URLs.

Place optional transparent icons in `--asset-dir` as `<asset_key>.png`. Missing files deliberately fall back to deterministic vector symbols, so a missing generated asset must not abort the whole figure. If a generated icon is used, generate it without text on a flat chroma background, run `remove_chroma.py`, inspect its alpha edge, and retain its provenance. The renderer emits SVG, PDF, PNG, and a hash manifest; run `audit_figure.py`, `qa_pdf.py`, and `check_public_release.py` before delivery.

An online planner may use an OpenAI-compatible structured-output call outside this standalone skill folder. Keep provider credentials and service routing in server-side environment configuration only. Use the repository-level `demo_core.reference_search` interface for reference metadata: `user-url` never fetches, and `wikimedia-commons` calls one fixed public API endpoint and filters to licensed raster records. An offline preset is acceptable for a stable demo only when the UI, figure, and manifest all disclose that it is a preset or `synthetic-demo`; never label it as a live model response.

## Link or transfer graph

Use `render_link_graph.py`. Nodes accept explicit coordinates or polar `angle` and `radius`. Solid Bézier paths encode tested or planned positive relations. Dashed red arrows encode an explicit unsupported or non-transfer claim.

```yaml
nodes:
  - {id: "probe", label: "Probe", angle: 90, radius: 1.0, color: "navy"}
  - {id: "world", label: "World", angle: -30, radius: 1.0, color: "orange"}
edges:
  - {source: "probe", target: "world", style: "nontransfer", color: "red", curvature: -0.28}
```

Line width may encode preregistered priority, not measured effect size, unless the caption explicitly says otherwise. Route labels and notes away from nodes and paths.

## Radar audit and GPU strong scaling

Use `render_audit_figure.py` for the paired audit view preserved from the reference paper: a polar baseline/candidate comparison beside a dual-axis GPU scaling panel. The radar duplicates color with dashed/solid lines and markers. The scaling panel uses the left axis for throughput and the right axis for efficiency or communication, optionally with low/high forecast bands and an ideal-linear reference. See `demo/source/advanced_audit.yaml` for both direct-array and CSV field names.

## Status-aware table

Use `render_table.py`. It produces a standalone TeX/PDF/PNG and a paper-ready TeX fragment.

```yaml
columns:
  - {header: "Method", align: "l", width_cm: 4.3}
  - {latex_header: "Recovery $\\uparrow$", width_cm: 2.3}
rows:
  - cells: ["Baseline", {latex: "72\\%^{\\mathrm P}", kind: "predicted"}]
  - style: "ours"
    cells: ["Ours", {latex: "\\textbf{94\\%^{\\mathrm P}}", kind: "predicted"}]
```

Use gray for forecast/design-time/synthetic-demo cells, blue for implemented or selected cells, violet for simulation, red tint for failed-gate, orange for invalid-objective or warning rows, and pale green only for truly measured cells. Preserve prediction markers in grayscale printing.

Each deterministic renderer writes `<output_name>_manifest.json` with evidence status, input paths, output paths, and SHA-256 hashes. Keep this beside the PDF; add citations/licenses and frame-selection details when the generic manifest cannot infer them.

## CUDA, GPU, and memory mechanisms

Start from `assets/tikz/mechanism_template.tex` and the requested palette. Treat official hardware diagrams as cited context. If simplifying a GPU block, show a projection/callout into the sourced architecture and label the local drawing `logical` or `schematic`.

For CUDA timelines:

- horizontal position means time;
- lanes mean streams, copy engines, or host control;
- kernels, transfers, events, and waits use distinct shapes;
- dependencies have explicit arrows or event markers;
- overlapping rectangles must represent actual overlap, not decoration.

## Real rollout panel

Use actual frames whenever the visual claims generated behavior. Align condition/action, observation, prediction, and ground truth by timestamp. Store original paths, crop coordinates, timestamps, action values, and selection policy in a manifest. A generated scene may illustrate an interface but cannot occupy the empirical result slot.
