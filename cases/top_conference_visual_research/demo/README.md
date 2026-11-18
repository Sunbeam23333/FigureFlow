# Synthetic data-figure demo

This tiny source pair exercises the two additions made for the research
registry: a quality–cost bubble plot (`size_field`, log x-axis, direct label)
and a line with a seed-like interval (`low`/`high`). Every number is synthetic
and the rendered figure must keep the `SYNTHETIC DEMO` status label.

```bash
python3 ../../../skill/design-research-figures/scripts/render_data_figure.py \
  quality_cost.yaml --output-dir /tmp/figureflow_top_conference_data
```

Replace the CSV only after recording the real experiment source, hardware,
seed count, aggregation rule, and evidence status in the caption/manifest.
