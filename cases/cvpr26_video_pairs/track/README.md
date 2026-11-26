# Paired trajectory edits with three qualitative cases

The official [Lee et al., CVPR 2026, Figure 1](https://openaccess.thecvf.com/content/CVPR2026/papers/Lee_Generative_Video_Motion_Editing_with_3D_Point_Tracks_CVPR_2026_paper.pdf#page=1) contains native image, clipping, path, text and font objects. This recipe reassembles those objects, not a screenshot or a copy of the original figure form. It is a **source-assisted** reconstruction. It does not generate new research results.

From the FigureFlow checkout:

```sh
python3 cases/cvpr26_video_pairs/track/build.py --source /path/to/track.pdf --out cases/cvpr26_video_pairs/local/track
```

The left PDF wraps the original author figure, verified against a saved-and-reopened independent paper-page crop. The right PDF starts with blank paper. It replays 26 separate native images, 51 separate paths, and 46 separate text paints with their inherited graphics state. The three regular/semibold embedded font subsets and original ICC profile, image soft masks and clip paths are retained. Image and font resources live in a blank local material PDF, not in this repository. The individual paint instructions, identities and z-order live in the editable local scene.

## Reuse with different evidence

Run the first command once to materialize the local scene. A subsequent replay needs only `scene.json` and its sibling `materials.pdf`. For example, create an `edits.json` next to the replacements:

```json
{
  "images": {
    "deform.input.back": "input-back.png",
    "deform.input.middle": "input-middle.png",
    "deform.input.front": "input-front.png",
    "deform.output.back": "edited-back.png",
    "deform.output.middle": "edited-middle.png",
    "deform.output.front": "edited-front.png"
  },
  "groups": {"deform.heading": [1, 0, 0, 1, 0, 2]}
}
```

```sh
python3 cases/cvpr26_video_pairs/track/build.py --scene cases/cvpr26_video_pairs/local/track/scene.json --overrides edits.json --out cases/cvpr26_video_pairs/local/custom
```

`custom.pdf` and `custom_receipt.json` are intentionally not called verified reproductions. Use authorized evidence, replace paired views together, and track its source in the new project's manifest. Source slots differ slightly in aspect; replacements must be explicitly cropped/padded to within 1% of the corresponding original. The six numbers are a PDF affine transform in figure coordinates, before paper scaling (1 unit = 0.39163 pt; positive y is up). For a single paint, use `"layers": {"joint.edited": [1,0,0,1,0,2]}`; for its mask, label and border to follow together, use `groups`. Paths and text runs can also be edited directly in the local scene. Newly introduced glyphs may require another licensed font: the author's font resource only contains the original subsets.

## Acceptance

- Require the pinned source checksum. The 1:1 receipt accepts **zero differing RGB channels** at 240 DPI and verifies the reference against the original proceedings page, independently of the reconstruction.
- Match all 26 decoded images and the 19 placed alpha masks to the original; compare the six transform coefficients per image to <0.001 pt, all in the observed paint order. The image digest provided by MuPDF identifies decoded display samples; SHA-256 separately pins the source and the generated files.
- Verify 14 editable label spans (content, PDF font and ink); preserve the eight frame stacks, paired case identities, six arrows and four heading rules.
- The numbered resource identifiers and back/middle/front denote publication-layer order, **not** absolute time, video frame number, or occluded content recovered by inference. The two 2D track projections are the real published images, not reconstructed 3D point coordinates.
