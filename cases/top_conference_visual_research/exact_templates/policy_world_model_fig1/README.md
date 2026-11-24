# Policy World Model — Figure 1

Source: Zhao et al., *From Forecasting to Planning: Policy World Model for
Collaborative State-Action Prediction*, NeurIPS 2025, [official PDF](https://papers.neurips.cc/paper_files/paper/2025/file/c3b3c5f9297ad0012cfe7188c34cea0e-Paper-Conference.pdf), page 2.

The claim is the three-way contrast between a conventional video model and
planner, separate tasks in a unified model, and the proposed policy world model
in which future forecasting informs planning. This is a transcription of a
published conceptual figure, not an independently evaluated result.

The vector diagram and text in `main.tex` are editable. The five photographs
are source-evidence tiles extracted locally from the official PDF by
`extract_assets.py`; no source photographs are committed. This is a
source-assisted reconstruction, **not a pixel-identical reproduction**:
font metrics, gradients, arrows, and tight image crops may differ. Use the
original source-locked crop for exact visual reference. The source crop on
page 2 has normalized top-left bbox `[0.176, 0.091, 0.824, 0.222]`.

Rebuild in an isolated working directory:

```bash
python3 cases/top_conference_visual_research/exact_templates/policy_world_model_fig1/render.py \
  /path/to/official-paper.pdf --output-dir /tmp/pwm_fig1
```

The `assets/source_manifest.json` records the PDF SHA-256, page, resolution,
and the exact crops. Check the original paper's reuse terms before distributing
the image tiles. Do not substitute invented images and call them paper results.
