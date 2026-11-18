# Source and evidence map

## Figure 1 — architecture / overview

- Final style source: `sources/figure1_style_refinement_revise.py`, variant `CO-F-original`
- Base topology source: `sources/figure1_architecture_render_v8.py`, function `architecture()`
- Paper evidence passages: `sections/02_method.tex`, `../code/concordrec/concordrec/model.py`, `../code/concordrec/concordrec/objectives.py`
- Local reference outputs: `reference/architecture.{svg,pdf,png,json}`
- Status: `illustrative` for the final presentation layer over an implemented
  topology; the figure does not encode a measured score.
- Key layout: asymmetric parallel branches, a magnified tokenwise allocation
  core, candidate/catalog evidence at right, and a separate offline rail.
- The final style script intentionally preserves the paper's post-processing
  step: it starts from an approved architecture SVG and an approved compact
  offline strip, then keeps labels/equations as editable vector nodes. The
  original upstream inputs are not duplicated here; the final output and the
  verbatim post-processing source are retained for provenance and diffing.

## Figure 2 — network structure

- Source code: `sources/figure2_network_render_v4.py`
- Original source role: `novelty_v4/render_network.py`
- Paper evidence passages: `sections/02_method.tex`, `sections/02_network.tex`
- Local reference outputs: `reference/network_structure.{svg,pdf,png,json}`
- Status: `illustrative` architecture specification; bars and posterior glyphs
  are schematic, not numeric results.
- Key layout: A/B/C semantic rails (navy/teal-violet/amber) plus a lower
  behavior-logit → modality-fusion → guided-logit output rail.

## Related retained inputs

- `sources/figure1_data.json` stores the source-bound support and published
  score examples used by the broader renderer; it is not a new result ledger.
- `assets/semantic_asset_provenance.json` records the text-free illustrative
  asset generation brief and rejected/accepted component roles.
- `assets/network_semantic_assets.png` is not an official logo or hardware
  diagram and must not be presented as measured evidence.

GridSlate and Omni-SID are not copied as primary templates here. Their source
figures may be consulted as comparative references, while CONCORD-Rec supplies
the default grammar for this FigureFlow route.
