# Derived visual grammar

These rules are distilled from the official figures listed in `catalog.json`.
They are design hypotheses for FigureFlow, not claims about any paper's
scientific result.

## Main-figure families

### 1. Hero evidence chain

Use a real image, frame strip, or measured input as the visual anchor on the
left. Put one compact representation in the center (point map, spectral volume,
token grid, or latent). Put the output evidence on the right: depth maps,
rollout frames, reconstructed video, task outputs, or an evaluation inset. The
reader should be able to follow `input → representation → evidence` without
reading every module label. VGGT and Generative Image Dynamics are the clearest
examples.

### 2. Action-conditioned rollout

Align each frame to a timestamp or action. A useful layout is:

```text
observation | a_t, Δt | model band | t+1 | t+4 | t+8 | goal / score
```

Use yellow/amber for actions, green/red only for good/bad score, and a single
method color for the model band. For world-model claims, real frames and a
goal/score are evidence; abstract mazes are only a schematic appendix.

### 3. Qualitative matrix

Rows are scenes/tasks or conditions. Columns are Input, Ground Truth, baselines,
and Ours. Keep crop, scale, and frame size fixed. Put runtime, view count, or a
small metric in a corner rather than adding a second legend. If a heatmap or
depth map is repeated, use one shared colorbar and identical limits.

### 4. Multiscale or staged training

Show the data object (image, grid, or tokens) in each stage, one representative
repeated block with `×L`/`×N`, and one dashed vertical stage separator. A stage
separator explains training semantics better than a row of duplicate cards.

### 5. Hub-and-spoke or semantic-band overview

Use a central model or simulator only when multiple input/output families really
share it. Otherwise prefer three columns—data/supervision → core computation →
capabilities/evidence—with a narrow semantic color band. Molmo/PixMo and UniSim
show why a few real examples often communicate more than many generic boxes.

## Data-figure families

### Quality–cost bubble

Use a log x-axis for time or compute when the range spans orders of magnitude.
Encode quality on y, parameter count by bubble area, and model family by color.
Draw a lower-bound or Pareto reference explicitly; label Ours directly and keep
the remaining labels short. Never let a bubble be the only carrier of a method
identity.

### Scaling law / learning dynamics

Use small multiples with shared semantic axes, one legend, sparse markers, and a
measured-point vs fitted-line distinction. Put the fitted equation or Pearson
correlation in a panel corner. A seed-derived interval is a band; a single run
is a line, not an invented uncertainty region.

### Text evidence + statistic

Place the concrete qualitative sample beside the z-score, p-value, ROC curve, or
token count that tests it. The sample is not a decorative example: its row and
metric must be tied by a shared label. The watermark figures are a good model.

### Annular or multi-metric comparison

One metric gets one local scale; do not imply that radial length across unrelated
metrics is a common unit. Direct labels and a stable method order are preferable
to a large legend. AlphaEdit and WeLM-Image are retained as executable examples.

### Qualitative + metric triptych

For video/world-model claims, use one fixed conditioning input and a matrix of
aligned frames first, then place the consistency/quality trade-off and temporal
metric curve beside or below it. Keep the method order identical in the grid,
the bubble/scatter, and any metric table. A black or gray dashed real-video
lower bound is more legible than a second saturated method color.

### Ablation small multiples

Use a 2×K or three-panel layout with shared y-limits. Columns should be the
hyperparameter or intervention; rows should be metric/task. Keep one global
legend and sparse markers. For mean curves, a translucent band is valid only
when its construction (seeds, bootstrap, or interval) is recorded. Inline metric
footers belong under qualitative tiles when the visual sample and its score are
inseparable.

### Evidence cascade

When a data-quality choice affects a model result, show the chain as
`distribution → filtered data → rank/coverage → downstream metric`. Dashed
grouping boxes and directional arrows can clarify causality, but each panel keeps
its own scale; do not place histograms, radars, and performance values on one
shared axis.

### Scaling extrapolation and phase transitions

Scaling figures use log-log axes, stable colors across facets, and a visible
observed-versus-predicted distinction. Put exponents, equations, and crossover
or extrapolation regions inside the panel. A phase transition is not a smooth
scaling law: use a vertical threshold guide and annotate the critical value
instead of fitting a decorative line through the jump.

### Uncertainty and robustness

For estimates, use density/violin plus a median marker, ordered swarms for
model-spec robustness, and a compact checkmark matrix for degrees of freedom.
Place 90%/95% intervals next to the estimate or in a clearly labelled ribbon;
never hide them in a legend or encode them as an unexplained pale band.

## Shared publication rules

1. White or very light background; grid and dividers are quiet.
2. Two to four semantic colors; preserve the same method color across panels.
3. Units and direction arrows (`↑`/`↓`) belong in axis labels or table headers.
4. Duplicate essential color distinctions with marker or line style.
5. Put hardware, seed count, crop policy, and evidence status in the caption or
   a compact footer; do not hide them in code only.
6. Use real frame strips or source images when the claim is visual; use a
   diagram only for a mechanism or a clearly marked schematic.
7. Prefer direct labels when a legend would cross the data. Keep labels short.
8. Repeat layers as `×L` and use a stage boundary instead of drawing every copy.
9. Tables report mean±std, OOM, and NA explicitly; never silently drop failures.
10. Run PDF font, clipping, grayscale, and final-size checks before delivery.

## Anti-patterns

* one saturated color per box with no semantic mapping;
* an AI-generated “architecture” that invents GPU/CUDA topology;
* a world-model rollout drawn as a maze without frames, actions, or timestamps;
* a confidence band on one seed;
* a 3-D chart or shadowed bubble used only for decoration;
* copied paper screenshots stored as unexplained assets;
* a claim-status label that says measured when the source is only illustrative.
