# PPT-native assembly for tiered pipeline figures

The tiered pipeline grammar is the reusable FigureFlow counterpart of the
reference Omni Embedding slide. It is not a screenshot template: every card,
connector, icon, label, and case crop remains an independent vector or image
layer. Use it for a pipeline or case-study figure when the reader must follow
parallel branches, a shared artifact, and downstream training/application.

## Fixed composition

Use the checked-in geometry in
[`assets/layouts/tiered_pipeline_reference.json`](../assets/layouts/tiered_pipeline_reference.json):

1. Three top source/representation modules (`y=28`, `h=300`);
2. Three aligned evidence modules (`y=426`, `h=308`);
3. One dark convergence bar (`x=341`, `y=790`, `w=918`, `h=79`);
4. A full-width training band (`x=32`, `y=916`, `w=1536`, `h=222`);
5. A compact application row below the band.

The canvas is 1600×1298 and the intended paper include width is 540 pt. Keep
the border at `#D5E0E9`, radius 18, and the accent rule at 5×40. The palette
assigns blue to source/raw evidence, teal to cleaned or paired evidence, amber
to temporal branches, violet to cross-case decisions and downstream use, and
navy to the single shared artifact. A color is never the only semantic cue.

## Connector and asset rules

- Route every cross-tier edge as an orthogonal elbow with a round junction dot.
- Use a separate native arrowhead at the terminal tangent; do not draw arrows
  into text or across a panel title.
- Keep real case thumbnails inside the panel that names their provenance.
- Use `contain` for logos and icons; never stretch an official mark.
- Keep generated imagery as a disclosed, low-opacity illustrative layer or omit
  it from the clean tiered route. It must not carry labels, formulas, metrics,
  or claimed outputs.
- Keep logo/source provenance and hashes in the manifest; use editable text for
  the brand name rather than asking an image model to redraw it.

## PPT-style assembly recipe

The reproducible sequence is:

1. Freeze the source hash, slide/page identity, and target frame.
2. Build a declarative scene with stable IDs and a symbol registry.
3. Validate geometry, text bounds, source licenses, and the preserve list.
4. Convert scene items one-by-one to native shape, text, edge, and image
   objects; split multiline text into separate lines.
5. Place raster/SVG assets with `contain` scaling. Preserve the source SVG and
   keep only a bounded PNG preview when the host needs one.
6. Export SVG, PDF, and PNG from the same current scene; write a manifest with
   hashes and evidence status.
7. Re-open the final page/deck and verify page count, title identity, object
   counts, font embedding, clipping, and unchanged non-target pages. A copied
   file that differs from the validated hash is a hard failure.

For a frame `[left, top, width, height]` and source canvas `(W,H)`, use

```text
scale = min(frame.width / W, frame.height / H)
ox = frame.left + (frame.width - W * scale) / 2
oy = frame.top  + (frame.height - H * scale) / 2
[x,y,w,h] -> [ox + x*scale, oy + y*scale, w*scale, h*scale]
```

This is a `contain` transform: never silently crop or stretch a source scene.
The companion case demo is
`cases/looped_comic_case_studies/build_tiered_looped_demo.py`; it produces
three source-bound case variants while retaining the older comic storyboard
renderer for comparison.

## Delivery manifest and logo gate

Use [`ppt_native_manifest.example.json`](../assets/layouts/ppt_native_manifest.example.json)
as the hand-off shape. Record the source deck hash, target title and physical
slide index, scene hash, frame/scale, native object counts, font minima, and a
post-publish reopen hash. A validation manifest is not enough: reopen the
published deck, read the XML slide order/title, and fail if the published hash
or target order differs.

Official logos are source assets, not image-model outputs. Keep the original
SVG/PNG, source URL/author/license/scope, and hash; allow only crop/viewBox or
format conversion. Put the brand name in editable text and preserve
`contain` placement. Never redraw, recolor, or silently substitute an official
mark.
