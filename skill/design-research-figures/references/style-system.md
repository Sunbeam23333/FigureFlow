# Shared Style System

The default theme lives in `assets/themes/academic_audit.json` and is loaded by the Python, SVG, and LaTeX demo modules. Change semantic tokens, not isolated hexadecimal values.

## Academic Audit palette

| Role | Token | Value |
|---|---|---|
| Primary ink | `navy` | `#142B4A` |
| Main series/contribution | `blue` | `#2A6FBB` |
| Faithful/measured/safe | `teal` | `#16827A` |
| Gate/warning/secondary | `orange` | `#E58B2A` |
| Alternate branch | `violet` | `#7A5195` |
| Explicit failure/non-transfer | `red` | `#B84A3A` |
| Secondary text | `gray` | `#647180` |
| Dividers | `line` | `#C8D5E2` |

Pastel tokens are for grouping and status, never for inventing new categories. Preserve semantic color roles across figures and tables.

For CUDA/runtime figures, a generic accelerator green is available under `assets/tikz/palette_gpu_green.tex`. The deterministic workflow renderer additionally supports `assets/themes/gpu_green_tech.json`: it maps the primary accent to `#63B246` and supplies background, card, rail, shadow, and semantic-light tokens. This is a generic technical theme: never use a third-party logo or imply endorsement, authorization, or affiliation. Emerald is suited to memory systems and rollouts. Warm Editorial is an optional paper-friendly alternative. Dark profiler palettes are best reserved for blogs, posters, or appendices.

The `welm-image-green` theme records a separate reference grammar from WeLM-Image Figure 1. Its radial data charts use a white/paper background, thin gray sector boundaries, pale-to-deep green method series, direct value labels, a white donut center, bold tangent metric labels, and a segmented outer accent arc. The published chart series are `#60AB88`, `#7ABE96`, `#93CDA7`, `#ACDCBB`, `#C3E7CD`, and `#DBF3E2`; the outer arc is `#3BBB74`. The public technical-report style defines the related base tokens `#07C160`, `#057A3E`, `#95EC69`, `#EAF8F0`, `#191919`, `#7A7E83`, and `#D9D9D9`. The source and license metadata are stored in `assets/themes/welm_image_green.json`. Keep the source reference in the figure manifest when reusing the palette.

The `concord-rec` theme is the retained CONCORD-Rec Figure 1/2 mechanism
grammar. Its core tokens are navy `#183B60` for the inherited behavioral
backbone, teal `#087F87` for trainable conditioning/fusion, violet `#8060AB`
for observed modality context and projections, and amber `#BC8320` for detached
offline supervision. Pale fills (`#F0F5FA`, `#EBF7F4`, `#F3EFF8`, `#FFF6E5`)
group the four semantic roles on white paper. Stacked cards denote repeated
states, trapezoids denote projections, hexagons denote fusion/loss operations,
and cylinders denote catalog/posterior stores. The source code and approved
vector references are retained under `cases/concord_rec_reference/`; use its
provenance/status manifest whenever adapting this grammar.

The top-conference research registry adds a generic white-paper token set in
`cases/top_conference_visual_research/palette_tokens.json`. Its default
semantic colors are emerald for the selected method, blue for measured model
families, amber for actions or controls, teal for latent/conditioning content,
violet for auxiliary context, and coral for a negative/contrast condition. The
registry also includes the Okabe–Ito-like series list
`#0072B2, #D55E00, #009E73, #CC79A7, #F0E442, #56B4E9, #000000` for charts where
color accessibility matters. Treat these as derived tokens rather than a
claim that any conference or paper endorses a palette.

## Typography modes

- **Illustrative overview:** Comic Sans MS, Comic Neue, or Chalkboard SE as a friendly display family; short technical labels only.
- **Quantitative figure:** DejaVu Sans, 8.5 pt native base, 10–10.5 pt panel titles, 7.3 pt legends, 7.4 pt ticks.
- **Formula:** STIX Sans path output or compiled LaTeX.
- **Paper/table:** the paper's body font; the demo uses TeX Gyre Heros/Arial for a neutral sans showcase.

Do not make Comic Sans the default for charts, tables, or body prose. Its role is a deliberate hand-drawn overview mode.

## Final-size calculation

For an SVG with viewBox width `W`, included at `T` points, a source font of `S` units appears at approximately:

`final_pt = S × T / W`.

Target at least 6.5 pt for meaningful figure body text; metadata footers may be smaller. Inspect both a single-column preview (about 3.25 in) and a double-column preview (about 6.75 in). If a five-stage overview cannot meet the floor, shorten labels, wrap deliberately, split the figure, or increase its paper span—do not rely on zoom.

For projected workflow figures, use `layout_preset: presentation-spacious`. It increases stage title, subtitle, body, and gate sizes by about 25%, wraps long titles instead of shrinking them, and limits each stage to two body lines. Keep `standard` as the backwards-compatible default. Verify the emitted `layout_qa` for all three layout families.

## Quantitative defaults

- hide top/right spines;
- axis line width around 0.8 pt;
- line width 1.8–2.5 pt;
- uncertainty fill alpha 0.08–0.14;
- grid alpha 0.18–0.20;
- markers duplicate color categories;
- PDF fonts use TrueType embedding (`pdf.fonttype = 42`);
- deliver vector PDF and 240 DPI PNG.

## Overview defaults

- paper-white background;
- card radius about 24 source units;
- inner block radius 16–18;
- subtle shadow (`dy=4`, blur about 7, opacity about 0.12);
- main arrows around 3 source units;
- separate ports for branch arrows;
- formulas as embedded path-only SVG;
- no raster text.

## Tables

Use booktabs, no vertical rules, 3–4 pt cell padding, 1.25–1.35 row stretch, and concise headers with units/direction arrows. The same semantic colors must mean the same evidence statuses in figures and tables.

## Accessibility and grayscale

Color cannot be the only encoding. Combine:

- line style with color;
- marker shape with series identity;
- direct status text with cell tint;
- arrow style with transfer semantics;
- labels or hatching with grouped bars.

Preview grayscale when the distinction supports a core claim.
