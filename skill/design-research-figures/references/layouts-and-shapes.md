# Layout, Shape, and Palette Library

Treat this as a combinatorial library. Choose by figure role and expand it when a new grammar fits better.

## Layout families

| Family | Best for | Typical structure |
|---|---|---|
| Butterfly | Two symmetric modes around a shared core | left wing → core ← right wing |
| Dual rail | Teacher/student, train/infer, host/device | parallel bands with cross-links |
| Ribbon | Long pipeline with changing state | curved or folded continuous band |
| Radial hub | One framework serving many tasks | central engine with differentiated spokes |
| Layered stack | Software/hardware or model/runtime | aligned horizontal strata |
| Timeline | CUDA streams, rollout steps, prefetch | time axis with lanes and events |
| Zoom/projection | Logical tile mapped to real hardware | overview + magnified inset |
| Split evidence | Mechanism plus qualitative result | schematic beside real case strip |
| Diagonal cascade | Progressive compression or refinement | staggered stages across page |
| Sankey/fan | Branching workloads or resource flow | width-encoded paths |
| Nested memory | tiers, residency, sparse/dense policy | containers with boundary crossings |
| Small multiples | ablation or mode comparison | repeated aligned mini-panels |
| Orbit | iterative world interaction | cyclic states/actions/observations |
| Cutaway | internal architecture with visible shell | outer system enclosing internal flow |

Avoid forcing all figures into rectangular boxes. Use paths, arcs, bands, lenses, braces, and whitespace as structural elements.

## Shape grammar

Assign stable meanings within a figure:

- rounded rectangle: ordinary compute stage;
- trapezoid or banner: kernel/transform with directional flow;
- diamond: event, condition, synchronization, or decision;
- cylinder: persistent storage;
- stacked sheets: tensor/cache/history;
- hexagon: fusion, merge, or coordinated target;
- circle: state, checkpoint, or atomic step;
- chevron: action/control input;
- bracket/brace: interval, overlap, or grouped region;
- film strip: actual sequence of frames only;
- lens/callout: projection into a detailed or sourced view;
- irregular organic field: environment/world, not computation.

Use line style too: solid for data, dashed for control or optional paths, dotted for provenance/projection. Always include a tiny legend if the encoding is not obvious.

## Icon strategy

An icon earns space only if it distinguishes meaning faster than text:

- camera: image/camera conditioning;
- directional controls or joystick: action conditioning;
- landscape frame: image input;
- distinct multi-frame strip: generated video;
- globe/scene layers: world state;
- robot/gripper: embodied action;
- waveform: audio or temporal signal;
- memory chips/shelves: storage tiers;
- event flag or lightning mark: synchronization.

Do not reuse one reel icon for T2V, camera control, action rollout, and generated world-model video.

## Palette families

### NVIDIA Green

- accent `#76B900`
- ink `#1A1A1A`
- graphite `#36393B`
- pale `#EDF7DA`
- paper `#F6F8F3`
- divider `#C9D0C2`

Works well for CUDA/runtime figures and white paper backgrounds.

### Emerald / Teal / Amber

- emerald `#0B6B45`
- teal `#087F8C`
- amber `#F2A900`
- mint `#E7F5EE`
- ivory `#FBFCF7`
- ink `#18342B`

Works well for memory mechanisms, rollouts, and system diagrams.

### Cool technical

- navy `#173F5F`
- blue `#20639B`
- cyan `#3CAEA3`
- warm highlight `#F6D55C`
- warning `#ED553B`
- paper `#F8FAFC`

### Warm editorial

- aubergine `#563D5D`
- coral `#D66D75`
- ochre `#D9A441`
- sage `#7A9E7E`
- cream `#FFF9F0`
- ink `#2D2730`

### Monochrome + one accent

Use grays for structure and a single accent for the paper's contribution. This is robust in print and helps prevent decorative color overload.

### Dark profiler

Use charcoal panels with green/cyan signals for blog, poster, or appendix traces. Avoid as the default main-paper figure unless the surrounding paper supports dark panels.

## Density controls

Increase useful density by:

- scaling the central mechanism;
- grouping related labels;
- embedding a small real case;
- tightening unused margins;
- replacing verbose prose with a formula or short tag;
- using an inset for detail.

Do not increase density by adding unrelated icons, repeated legends, or ornamental boxes.
