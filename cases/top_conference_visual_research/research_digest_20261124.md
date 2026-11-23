# FigureFlow visual research digest — 2026-11-24

This survey records source-grounded layout grammar, palette roles, bbox notes,
and native-renderer rules. It does not vendor paper screenshots or claim that
FigureFlow reran any experiment. Exact entries remain `published-figure`
evidence and use the source-locked PDF route for 1:1 visual identity.

## Main figures and qualitative evidence

| Paper / figure | Official source | Reusable grammar | Key rule |
|---|---|---|---|
| Navigation World Models, CVPR 2025 Fig. 1 | [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Bar_Navigation_World_Models_CVPR_2025_paper.pdf) | `action_rollout` + `hero_evidence` | align action/time with frame rails; reserve green/red for score semantics |
| World-consistent Video Diffusion, CVPR 2025 Fig. 1–3 | [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Zhang_World-consistent_Video_Diffusion_with_Explicit_3D_Modeling_CVPR_2025_paper.pdf) | `hero_evidence_plus_task_fan`, `paired_evidence`, `projection_inset` | keep RGB/XYZ pairs together; keep the red condition box and `×N` block stable |
| MaskGWM, CVPR 2025 Fig. 1 | [HTML](https://openaccess.thecvf.com/content/CVPR2025/html/Ni_MaskGWM_A_Generalizable_Driving_World_Model_with_Video_Mask_Reconstruction_CVPR_2025_paper.html) | `action_rollout_plus_mask_band` | mask tokens form a temporal band, not decorative blobs |
| GEM, CVPR 2025 Fig. 1 | [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Hassan_GEM_A_Generalizable_Ego-Vision_Multimodal_World_Model_for_Fine-Grained_Ego-Motion_CVPR_2025_paper.pdf) | capability matrix / evidence atlas | keep capability and domain rows aligned; frames remain evidence tiles |
| ReconDreamer, CVPR 2025 Fig. 1 | [HTML](https://openaccess.thecvf.com/content/CVPR2025/html/Ni_ReconDreamer_Crafting_World_Models_for_Driving_Scene_Reconstruction_via_Online_CVPR_2025_paper.html) | `online_restoration_loop` | distinguish restoration from generation; dashed feedback is only online update |
| Wonderland, CVPR 2025 Fig. 1 | [HTML](https://openaccess.thecvf.com/content/CVPR2025/html/Liang_Wonderland_Navigating_3D_Scenes_from_a_Single_Image_CVPR_2025_paper.html) | `single_image_to_world_hero` | one real input anchors a compact novel-view strip |
| DINO-WM, ICML 2025 | [PMLR](https://proceedings.mlr.press/v267/zhou25t.html) | action-conditioned world-model chain | keep visual state, action, prediction, and planning rails distinct |
| Policy World Model, NeurIPS 2025 Fig. 1 | [PDF](https://papers.neurips.cc/paper_files/paper/2025/file/c3b3c5f9297ad0012cfe7188c34cea0e-Paper-Conference.pdf) | `comparison_progression` | compare conventional / unified / policy-world-model routes with identical anchors |
| WorldModelBench, NeurIPS 2025 Fig. 1 | [OpenReview PDF](https://openreview.net/pdf/db141a241c347e8967ff27c7551d22aa3d5cabe3.pdf) | `qualitative_metric_contrast` | place real video evidence beside visual-quality and physical-law check tables |

## Data and result figures

| Paper / figure | Official source | Reusable module | Visual rule |
|---|---|---|---|
| Scaling Laws for Optimal Data Mixtures, NeurIPS 2025 Fig. 1 | [PDF](https://openreview.net/pdf/0c763c984dae4c3b82805d215708d4f45f9f9814.pdf) | `scaling_law_dual_panel` | shared legend; model-size marker; observed/predicted line style; forecast ribbon |
| Alignment of Unimodal Vision and Language Models, CVPR 2025 Fig. 2 | [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Zhang_Assessing_and_Learning_Alignment_of_Unimodal_Vision_and_Language_Models_CVPR_2025_paper.pdf) | `dual_bubble_alignment` | bubble radius = parameters; fitted line; separate modality legends |
| Mixture-of-Scores, ICCV 2025 Fig. 2–4 | [PDF](https://openaccess.thecvf.com/content/ICCV2025/papers/Wu_Mixture-of-Scores_Robust_Image-Text_Data_Valuation_via_Three_Lines_of_Code_ICCV_2025_paper.pdf) | `benchmark_bubble_strip`, `disparity_scatter_line` | categorical separators; keep density and trend panels separate |
| Visual Consensus Prompting, CVPR 2025 Fig. 2 | [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Wang_Visual_Consensus_Prompting_for_Co-Salient_Object_Detection_CVPR_2025_paper.pdf) | `quality_cost_bubble` | overlapping translucent bubbles plus improvement arrows |
| SLVR, CVPR 2025 Fig. 1 | [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Ni_SLVR_Super-Light_Visual_Reconstruction_via_Blueprint_Controllable_Convolutions_and_Exploring_CVPR_2025_paper.pdf) | `quality_cost_bubble_inset` | connected red “ours” path and nested compute-size key |
| Scalable Autoregressive Monocular Depth, CVPR 2025 Fig. 2 | [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Wang_Scalable_Autoregressive_Monocular_Depth_Estimation_CVPR_2025_paper.pdf) | `model_size_scaling_scatter` | explicit metric direction and connected model-family path |
| ParetoFlow, ICLR 2025 Fig. 1 | [OpenReview PDF](https://openreview.net/notes/edits/attachment?id=4NLHepEXMS&name=pdf) | `pareto_frontier_triptych` | shared axes/legend; native Pareto curve; stars and dashed trajectories |
| Scaling Exponents Across Parameterizations, ICML 2024 | [PMLR](https://proceedings.mlr.press/v235/everett24a.html) | `scaling_small_multiples` | shared log axes, stable line-style legend, explicit fit semantics |

## Accumulated tokens and integration contract

- Paper: `#FFFFFF` / `#F7F9FC`; ink: `#16314D` / `#1A1A1A`.
- Source/reference: blue `#347AC4`; latent/geometry: teal `#008C86` or emerald
  `#0B6B45`; action/control: amber `#C78337`; decision/failure: violet
  `#7953B4`; red is reserved for bad score or failed gate.
- Dividers: `#D5E0E9`; evidence backgrounds: pale blue, mint, cream, lavender.
- At 540 pt include width, reject any frame label, action marker, score badge,
  legend, or axis label that is not readable after PDF rendering.

Each future exact entry records `source_url`, PDF page, normalized top-left crop
bbox, layout family, reading order, palette roles, typography, marker/legend
registry, `evidence_status: published-figure`, and
`paper_include_width_pt: 540`. Native SVG/TikZ owns labels, axes, formulas,
arrows, and data marks; source crops are only the 1:1 QA/reference route.
