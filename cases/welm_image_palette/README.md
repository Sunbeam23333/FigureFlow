# WeLM-Image green radial-chart style

This is a deterministic style demo that applies the WeLM-Image Figure 1 radial-chart palette and segmented outer arcs to five published AlphaEdit metrics. The values remain `published-figure` observations from the AlphaEdit source audit. The chart is a style adaptation, not a reconstruction of WeLM-Image Figure 1.

```bash
python -m demo_core.data_analysis cases/welm_image_palette/alphaedit_short.csv \
  --chart annular --palette welm-image --title "AlphaEdit · WeLM green" \
  --focus-method AlphaEdit --output-dir demo/output/welm_image_palette
```

The reusable tokens live in `skill/design-research-figures/assets/themes/welm_image_green.json` and `skill/design-research-figures/assets/tikz/palette_welm_image.tex`. The palette provenance points to WeLM-Image Figure 1 and its public technical-report style file.
