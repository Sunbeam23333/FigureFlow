# Evidence-Grounded Figure Workflow

## 1. Write the semantic contract

Before choosing a layout, create a compact table:

| Field | Required content |
|---|---|
| Figure claim | One sentence the reader should remember |
| Inputs | Data, prompts, actions, states, caches, or parameters |
| Transformations | Ordered computation or conceptual stages |
| Outputs | Predictions, videos, losses, updates, metrics |
| Parallelism | What overlaps, synchronizes, shards, or pipelines |
| Invariants | Facts that must remain true in every candidate |
| Evidence | Paper line, code symbol, config, log, profiler, or cited source |
| Illustration | Anything that is only explanatory or decorative |

Resolve disagreement in this order: runnable implementation and measured traces, current paper text, design notes, then assumptions. Flag mismatches instead of silently choosing one.

## 2. Separate evidence layers and statuses

Use four layers while assigning one canonical status to the visual:

1. **Measured:** profiler trace, memory number, throughput, generated output.
2. **Implemented:** code path, scheduling rule, loss function, cache policy.
3. **Explained:** abstraction that accurately summarizes implementation.
4. **Illustrative:** icon, scene, simplified block, or conceptual background.

Visual style must not blur these layers. Label illustrations and show measured cases in recognizably empirical panels.

Allowed primary statuses are:

- `measured`: reported from a trace, experiment, or dataset row;
- `implemented`: supported by the runnable code path but not yet a scientific result;
- `simulation`: computed from an explicit simulator or analytical model;
- `forecast`: design-time prediction awaiting measurement;
- `illustrative`: conceptual topology or generated explanatory asset;
- `synthetic-demo`: fabricated only to demonstrate rendering behavior.
- `failed-gate`: a measured or completed test that missed a prespecified criterion; retain it visibly.

Mixed-status visuals must mark the exceptional cells, curves, panels, or assets individually. The status also belongs in the manifest.

## 3. Create a content inventory

For every component, record:

- canonical short label;
- optional formula;
- visual role: source, transform, store, event, result, control, or metric;
- unique visual cue;
- required connections;
- whether it needs a real thumbnail;
- minimum readable size.

Delete components that repeat caption prose without clarifying structure.

## 4. Make rough candidates

Start with grayscale wireframes. Candidate exploration should test composition before polished rendering:

- 3 or more layout families;
- compact and spacious density variants;
- at least one low-icon vector-first version;
- at least one case-integrated version when qualitative output matters;
- a palette pass only after structure works.

Use stable IDs. Keep a one-line rationale and failure mode for each candidate.

## 5. Refine a selected direction

Refine in this order:

1. factual flow and ordering;
2. grouping and hierarchy;
3. shape semantics;
4. case-study evidence;
5. typography and formulas;
6. palette;
7. decoration and micro-spacing.

This order makes component replacement cheap and prevents a beautiful raster base from locking in an incorrect mechanism.

## 6. Hardware and systems diagrams

Distinguish:

- physical hardware blocks;
- logical software tiles;
- CUDA streams and events;
- kernels and fused operators;
- buffers/caches;
- host/device control.

If simplified blocks are used, project them into a sourced architecture view using a callout, inset, or zoom lens. Cite the hardware source in the caption or paper, not inside every block.

## 7. Delivery

Deliver:

- editable source;
- vector PDF;
- review PNG;
- source CSV or frame manifest when applicable;
- candidate gallery when applicable;
- provenance note for real/generated assets;
- final paper-page screenshot rendered from the current PDF;
- a short semantic audit stating what was verified.
