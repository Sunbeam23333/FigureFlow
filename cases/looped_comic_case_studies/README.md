# Looped Transformer comic-style case-study demos

This demo package keeps the selected Looped Transformer B_cir/v13 ideas as
case content, but renders the final figures with the clean, grid-first
`tiered_pipeline_reference` grammar extracted from the approved FigureFlow
Omni Embedding/PPT case. The result is a native-vector workflow rather than a
watercolor background with loosely placed cards.

Three hypothetical paper ideas are included:

1. **Looped Visual State** — refine a parkour state without locking in missing evidence.
2. **Looped Active Sensing** — refine a laboratory grasp, then refresh the view.
3. **Looped World State** — recheck an autonomous-vehicle scene before committing an action.

The primary route uses three top modules → three evidence modules → a shared
dark artifact → a two-lane training band → an application row. All labels,
arrows, icons, panel geometry, and status text are deterministic SVG layers;
real case images remain independent evidence layers. Generated comic images
are retained as provenance assets and are deliberately omitted from the clean
tiered route so they cannot compete with the process or imply measured output.
The older storyboard route remains available in `build_looped_comic_demo.py`
for comparison and writes only to `rendered/comic_storyboard/`, so it cannot
overwrite the primary tiered files.

## Outputs

- `rendered/looped_parkour_refine.png` / `.pdf` — parkour state refinement
- `rendered/looped_robot_active_sensing.png` / `.pdf` — active sensing/grasp
- `rendered/looped_autonomous_vehicle.png` / `.pdf` — world-state recheck
- `rendered/*_review.png` — 240-DPI paper-width review renders
- `rendered/manifest.json` — layout ID, status, hashes, source captions, and output sizes
- `rendered/tiered_scene.json` — editable layout/evidence scene contract
- `sources/manifest.json` — source URLs, licenses, and evidence roles

Rebuild with:

```bash
python3 cases/looped_comic_case_studies/build_tiered_looped_demo.py
```

The reusable layout contract is
`skill/design-research-figures/assets/layouts/tiered_pipeline_reference.json`;
the PPT-native assembly and contain-scaling rules are in
`skill/design-research-figures/references/ppt-native-assembly.md`.

The two online case photos are from Wikimedia Commons: a public-domain NIAID
assay-plate image and a CC BY 2.0 autonomous-vehicle image. The parkour case
uses the project-local LoopedTransformer research crop. The generated assets
are illustrative backgrounds only; they are not model outputs or measurements.
