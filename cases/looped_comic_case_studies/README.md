# Looped Transformer comic-style case-study demos

This demo package applies the selected Looped Transformer B_cir/v13 visual
grammar to three hypothetical paper ideas:

1. **Looped Visual State** — refine a parkour state without locking in missing evidence.
2. **Looped Active Sensing** — refine a laboratory grasp, then refresh the view.
3. **Looped World State** — recheck an autonomous-vehicle scene before committing an action.

Each output combines a text-free GPT-image-2 watercolor/ink background, a real
case-study image layer, native labels and arrows, and an explicit boundary on
what the illustration does not prove. Generated images contain no text or
scientific geometry; all labels and arrows are added deterministically by
`build_looped_comic_demo.py`.

## Outputs

- `rendered/looped_parkour_refine.png` / `.pdf`
- `rendered/looped_robot_active_sensing.png` / `.pdf`
- `rendered/looped_autonomous_vehicle.png` / `.pdf`
- `sources/manifest.json` — source URLs, licenses, and evidence roles

The two online case photos are from Wikimedia Commons: a public-domain NIAID
assay-plate image and a CC BY 2.0 autonomous-vehicle image. The parkour case
uses the project-local LoopedTransformer research crop. The generated assets
are illustrative backgrounds only; they are not model outputs or measurements.
