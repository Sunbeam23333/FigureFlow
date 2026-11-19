# Case-study-in-flow composition

Use this grammar when a paper's main method figure needs to show both the
mechanism and a real qualitative case. The case is not a decorative thumbnail:
it is an evidence layer that enters at the input, passes through the relevant
stages, and reappears at the output with a compact metric or failure marker.

## First decide which figure role this is

The attached top-conference writing guide separates two jobs that are often
mistakenly merged:

- **Figure 1 teaser:** a compact showcase of the failure phenomenon. Use a real
  frame sequence plus a single diagnostic curve; show the task, concept, and
  failure, but do not reveal the method's cause or repair.
- **Framework / method figure:** a left-to-right `Input → 1 → 2 → 3 → 4 →
  Output` figure. Here a real case may be embedded in the flow to demonstrate
  what each stage does. The module numbers, names, and reading order must match
  the Method section exactly.

Do not put failure, causal explanation, full method, and final result into the
same teaser. If a figure answers more than one of those questions, split it.

## Three reusable layouts

### 1. Evidence ribbon

Use a horizontal or gently folded ribbon for the computational path. Place a
borderless frame strip on the ribbon at the input, an intermediate crop or
latent visual at the stage that changes it, and the final frame strip at the
output. Use a thin colored contour around the case image, not a card around
every element. The case is visually continuous even when the computation is
shown in blocks.

### 2. Cutaway / zoom projection

Use a compact framework overview, then project one stage into a larger inset
that contains the real frame sequence, formula, and a one-line metric. The
projection line must identify the same stage number and preserve the source
crop. This is appropriate when the main figure would otherwise become too
dense for a single-column width.

### 3. Dual rail with case cross-links

Use an upper rail for the implemented computation and a lower rail for the
real case (`frame → state → frame`). Cross-links are only drawn where a stage
consumes or produces the case evidence. Solid lines mean data, dashed lines
mean control/conditioning, and dotted lines mean a projection or explanatory
mapping. This is useful for world-model rollout, teacher/student, and
train/infer diagrams.

## Geometry and asset rules

- Keep real case assets borderless or lightly framed; reserve rounded cards for
  computation, storage, and status gates.
- Use a true film strip only for a frame sequence. A single frame is a landscape
  panel, not a film reel.
- Overlap is allowed when it creates a semantic relationship: a frame strip may
  overlap a stage boundary to show where the observation enters, and an inset
  may overlap the framework with a projection lens. Decorative overlap is not
  allowed.
- Keep the original aspect ratio of every case crop. Record source, crop,
  timestamp/frame index, resize, and whether the asset is measured, implemented,
  illustrative, or synthetic-demo.
- Add the metric or failure marker adjacent to the case, not inside a dense
  computational node. The reader should be able to distinguish visual evidence
  from the mechanism in three seconds.
- Use one semantic color for the paper's contribution and neutral structure for
  context. Use red/orange only for an observed failure or failed gate.

## Manifest contract

```yaml
layout_family: case-study-in-flow
evidence_status: implemented
case_panels:
  - id: case_input
    source: assets/cases/scene_07.png
    crop: [0.02, 0.04, 0.97, 0.94]
    frames: [0, 6, 12, 18]
    role: input-observation
    status: measured
  - id: case_output
    source: assets/cases/scene_07_output.png
    role: output-evidence
    status: measured
    metric: "Contact failure rate = 0.08"
projection_links:
  - {source: stage_2, target: case_input, style: dotted}
```

The final output must include the editable composition, the original uncropped
asset, the frame/crop manifest, a paper-width render, and a caption that states
what the case establishes and what it does not establish.
