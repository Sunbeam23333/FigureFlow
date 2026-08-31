# Raster Assets, Real Cases, and Prompt Patterns

## Source priority

Use assets in this order:

1. actual outputs from the project;
2. benchmark or dataset samples with attribution and compatible use;
3. user-provided photographs or screenshots;
4. generated illustrative assets;
5. abstract vector placeholders.

Never replace an expected empirical case study with generated art without disclosure.

## Reference provider boundary

When the repository-level FigureFlow app is available, select one provider explicitly:

- `offline-example`: deterministic and network-free;
- `user-url`: validate and store the URL only; never fetch, proxy, thumbnail, or follow redirects;
- `wikimedia-commons`: query only the fixed Commons MediaWiki API and retain raster results with a source page and license metadata.

Store title, original asset URI, source page, author, license name/URL, provider, and attribution in `FigurePlan.reference_assets`. A search result is a reference candidate, not automatic permission to reuse. Do not send arbitrary provider URLs to the renderer or background-removal tools.

## Real rollout cases

For video/world-model rollouts:

- preserve temporal order;
- use consistent crop and aspect ratio;
- show actions or conditions aligned to frames;
- distinguish observations, predictions, and ground truth;
- label horizons or timestamps;
- avoid cherry-picked frames that hide failure transitions;
- keep the unmodified source strip for provenance.

If a strip is packed into one image, use `scripts/extract_frames.py` for equal crops, then adjust crops only when the source geometry requires it.

## ImageGen rules

Use ImageGen for text-free bitmap elements such as:

- a clean camera-control icon;
- an action-conditioned driving or robotics scene;
- a world/environment vignette;
- a transparent-friendly visual metaphor;
- a consistent family of domain icons.

Do not ask ImageGen to render labels, formulas, charts, precise GPU architecture, CUDA timelines, or measured results.

## Prompt skeleton: component

> Create one text-free research-paper illustration of [semantic object]. Clean vector-like 3D/isometric style, immediately recognizable at 24 mm width, [palette] accents, simple silhouette, no letters, no numbers, no symbols resembling text, no border, centered, isolated on a flat chroma background [color], generous empty margin, consistent soft lighting.

## Prompt skeleton: qualitative illustration

> Create a text-free illustrative [driving/robotics/world] temporal scene for a research framework diagram. Show [observable change caused by action] with realistic spatial continuity, clean paper-friendly lighting, restrained [palette] accents, no UI, no labels, no watermarks, no film-reel motif. This is an explanatory illustration, not a claimed model output.

## Prompt skeleton: icon family

> Create a coherent set of separate, text-free icons for [list]. Each icon must have a unique silhouette and semantic cue, consistent stroke weight and perspective, no shared film-reel shortcut, no labels, isolated on a transparent-friendly flat background, paper-ready at small size.

## Background removal

Prefer an exact solid chroma background that does not occur in the object. Remove it by color distance, inspect anti-aliased edges, and export PNG with alpha. Never erase pale internal details by using an overly broad threshold.

Use the bundled soft-matte tool for `#00ff00` assets:

```bash
python3 "$FIGURE_SKILL_ROOT/scripts/remove_chroma.py" raw_icon.png processed_icon.png \
  --key '#00ff00' --transparent-distance 24 --opaque-distance 105 \
  --despill 0.88 --manifest processed_icon.json
```

Inspect the processed icon on white, dark, and final card backgrounds. A low `mean_edge_key_excess` is useful evidence that despill worked, but it does not replace visual inspection.

## Provenance note

Record:

- asset filename;
- source path or URL;
- crop/resize operations;
- ImageGen prompt and date if generated;
- whether it is real output, dataset sample, photograph, or illustration;
- required citation or license note.

Keep provenance in a nearby text or JSON file when the project has no asset manifest.
