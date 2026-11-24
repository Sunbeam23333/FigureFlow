# CARE Transformer Figure 1: data-grounded reconstruction

Reconstructs the accuracy–latency–compute chart from Zhou et al., CVPR 2025,
using values transcribed from their Table 1. The paper's reported measurement
supports the visual comparison; it is **not** a newly run experiment.

- Paper: https://openaccess.thecvf.com/content/CVPR2025/papers/Zhou_CARE_Transformer_Mobile-Friendly_Linear_Visual_Transformer_via_Decoupled_Dual_Interaction_CVPR_2025_paper.pdf
- Version inspected visually: https://arxiv.org/pdf/2411.16170 (Figure 1, p. 1; Table 1, p. 5)
- Author repository: https://github.com/zhouyuan888888/CARE-Transformer
- Editable data: `data.csv`; render with `python3 render.py`.
- Plot shows Top-1 ImageNet-1K accuracy, latency in ms, and GMACs as marker area.

The chart's device is not named in the original axis. Its coordinates match
the **RTX 4090 batch-64** latency column of Table 1 (for example CARE-S0,
S1 and S2: 9.8, 14.2, 20.4 ms); that correspondence is an inference from
the figure and table, not an explicit figure-caption statement. Table 1 says
the GPU batch size is 64. The omitted MobileAtt-PVT-v2-B0 point has latency
17.7 ms but the source figure displays the DeiT-T/DeiT-S path only.

**Fidelity boundary:** the data values and graph grammar are sourced; marker
area scaling, line opacity, typography, and label placement are approximations
inferred from the published figure. This is not the authors' plotting code and
is **not pixel-identical**. Inspect the original PDF directly for exact appearance.
Do not treat the source plot as a newly reproduced benchmark, or use these
values for different hardware or batch sizes.
