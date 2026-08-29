# Paper Figure QA

## Semantic audit

- The figure supports one clear claim.
- Every stage, arrow, formula, and ordering matches paper/code evidence.
- Physical hardware is not confused with software scheduling.
- Measured outputs are visibly distinct from illustrations.
- Generated assets are not described as model results.
- Icons have unique meanings and do not contradict labels.

## Composition audit

- Reading order is obvious without the caption.
- The contribution has the strongest visual emphasis.
- Related items are grouped by proximity and alignment.
- Empty space creates hierarchy instead of accidental holes.
- No repeated decorative containers make all components look identical.
- A reader can understand the structure at page width.

## Typography audit

- Text and formulas are vector-rendered.
- No AI-generated text is embedded in raster assets.
- Font choice is consistent and legally/technically available.
- Meaningful body text remains at or above roughly 6.5 pt at final include width.
- Labels are short; long explanation lives in the caption.
- Math notation matches the paper.

## Color audit

- Contrast is sufficient on paper-white and grayscale print.
- Color is not the only carrier of meaning.
- Accent colors identify contribution, state, or event consistently.
- Background tint is subtle enough for conference PDF viewing.
- Dark themes are used intentionally, not by default.

## Geometry audit

- No arrows, braces, labels, or icons cross the crop boundary.
- Arrowheads do not cover text or nodes.
- Rounded boxes have consistent radii and padding.
- Strokes remain visible after scaling.
- Raster cases have consistent crop and resolution.
- The PDF page has no accidental second page.

## Candidate-set audit

- Candidates vary in structure, not only color.
- At least three layout families were considered.
- There is a compact and a spacious version.
- Candidate IDs map to editable source files.
- The selected version preserves the best mechanism and palette decisions independently.

## Final render loop

1. Compile PDF.
2. Render PDF to PNG at 180–300 DPI.
3. Run `audit_figure.py` for edge occupancy and `qa_pdf.py` for page/font/log checks.
4. Inspect the whole figure and both single- and double-column previews when applicable.
5. Create a contact sheet for multiple candidates.
6. Fix all visible overlap, clipping, ambiguity, false evidence, stale-page previews, Type 3 fonts, unembedded fonts, and LaTeX warnings.
7. Recompile and re-render pages from the final PDF; record its hash when a paper build relies on cached previews.

## PDF and LaTeX audit

- Each standalone figure/table PDF has exactly one page.
- The expected paper page count matches the current PDF, not an old render directory.
- Fonts are embedded and no Type 3 font is present.
- Compile logs contain no `Overfull`, undefined references/citations, emergency stop, or fatal error.
- SVG formulas contain path/image output rather than raw `\\frac` or `$...$` text.
- Paper screenshots are generated after the last compile and visually inspected.
