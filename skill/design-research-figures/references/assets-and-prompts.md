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
- `wikimedia-commons`: query only the fixed Commons MediaWiki API and retain raster results with a source page and license metadata; an explicitly selected result can then be safely imported.

Store title, original asset URI, source page, author, license name/URL, provider, and attribution in `FigurePlan.reference_assets`. A search result is a reference candidate, not automatic permission to reuse.

For a selected Commons result, bind the run to the exact previewed result ID and use `demo_core.reference_import` rather than a generic URL client. The importer permits only its fixed `upload.wikimedia.org` / `thumb.wikimedia.org` host allowlist, refuses redirects, caps response bytes and decoded pixels, verifies JPEG/PNG/WebP bytes against both HTTP and search metadata, requires an allowlisted CC/Public Domain record with source and attribution, strips embedded metadata, and writes a local PNG plus provenance manifest. Only the local PNG may enter crop/matte/layout processing; never send its pixels to a model. `user-url` stays record-only. A local uniform-border matte is allowed when its measurable gate passes; otherwise keep the photographic background and disclose that no semantic cutout was performed. If the imported image enters the canvas, keep its visible title/creator/license/source/modification credit on every rendered SVG/PDF/PNG and retain the full source/license URLs in SVG metadata and the manifest.

## Official marks and repeated semantic symbols

Official logos are an exception to generative illustration: retrieve the actual
official mark, retain its original bytes, source page, content hash and any crop
record. Never AI-redraw, recolor, chroma-key or invent a product/version badge.
Keep the exact version name in a separate editable text layer when the mark is
only a family brand. Official provenance does not grant trademark rights.

The research harness supports `search_assets(provider="official-brand")` using
a small vetted primary-source catalog, followed by registered-ID import. This
is not web-wide search. Downloads are bounded, redirect-free and checksum-pinned;
unrecognized URLs never become network instructions. Unknown marks require an
explicit user asset/source record; do not improvise a lookalike logo.

For repeated methods, bind the same canonical asset/shape under one concept in
`metadata.symbol_registry` and reference it from `metadata.concept_bindings`.
Use set overlap for Jaccard and a vector-angle cue for cosine similarity when
appropriate; do not reuse an unrelated generic search icon for both. These are
visual conventions, not measured quantities. Registry QA establishes declared
consistency, not scientific correctness. Different branch colors are allowed.

Use the safe native SVG importer for simple original SVGs. Keep registered SVG
bytes for rendering and generate the model's PNG preview from those same bytes.
Retain a verified raster fallback for unsupported complex SVG features rather
than weakening the script/external-resource/DTD restrictions. Do not let two
assets' gradient or clip IDs collide. Inspect on the final background and at
presentation size before acceptance.

The research harness's explicit online authorization permits registered asset
previews in its model context. The earlier Commons-only standard workflow's
local-pixels rule does not apply to that separately authorized research run.

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
