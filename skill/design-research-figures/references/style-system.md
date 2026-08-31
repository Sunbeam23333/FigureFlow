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
