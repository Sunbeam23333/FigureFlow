# Research Visual System Demo

This self-contained demo exercises the four core deterministic modules in the skill. All numbers are synthetic and are marked `synthetic-demo`; none are paper results.

Run from any directory:

```bash
python3 /absolute/path/to/design-research-figures/scripts/build_visual_demo.py \
  --output-dir /absolute/path/to/design-research-figures/demo/output
```

The build creates:

- `demo_main_overview.svg/pdf/png`: five-stage semantic overview, path-rendered formulas, branch routing, and hard gates;
- `demo_quantitative.pdf/png`: four panels backed by deterministic source CSVs;
- `demo_link_graph.pdf/png`: weighted transfer links and an explicit dashed non-transfer edge;
- `demo_results_table.tex/pdf/png`: standalone result table plus a paper-ready fragment;
- `demo_paper.tex/pdf`: compiled A4 two-column paper layout;
- `demo_paper_page-*.png`: fresh page renders made after the final compile;
- `demo_gallery.png`: visual contact sheet;
- `demo_manifest.json`: sources, status, hashes, and artifact paths;
- `<module>_manifest.json`: renderer-level evidence status, inputs, outputs, and hashes;
- `qa_single_page.json` and `qa_paper.json`: page-count, dimension, font, and LaTeX-log audits.

The optional radar + GPU strong-scaling module has its own source at `source/advanced_audit.yaml`:

```bash
python3 /absolute/path/to/design-research-figures/scripts/render_audit_figure.py \
  /absolute/path/to/design-research-figures/demo/source/advanced_audit.yaml \
  --output-dir /tmp/advanced-audit-demo
```

Edit the declarations under `source/`, not the rendered artifacts. The source CSVs are regenerated in `output/source_data/` with seed `20260825`.
