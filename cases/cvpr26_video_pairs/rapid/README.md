# RAPID Figure 1 — aligned method × displayed-frame matrix

The [CVPR 2026 paper, p. 1](https://openaccess.thecvf.com/content/CVPR2026/papers/Lin_RAPID_Reusing_Attention_Sparsity_with_Inter-step_Adaptation_for_Efficient_Video_CVPR_2026_paper.pdf#page=1) prints Figure 1 as one 2062 × 1016 JPEG. This recipe rebuilds the composition from **15 independent author frames, 46 words, and the measured spacing**. It does not run RAPID or infer frame timestamps. The left-hand frame has only 402 published pixels; do not normalize it to the other columns’ 413 pixels. Keep the four 2-pixel gutters.

```sh
python3 cases/cvpr26_video_pairs/rapid/build.py --source /path/to/rapid.pdf --out cases/cvpr26_video_pairs/local/rapid
python3 -m pytest cases/cvpr26_video_pairs/rapid/test_replay.py
```

| Local output | Intended use |
|---|---|
| `reference.pdf` | The original JPEG at the exact PDF placement size, without resizing or recompression. |
| `seamless.pdf` | **Print comparison.** Each component is read back from its own file and placed onto a fresh paper-white canvas, which is verified byte-for-byte against the author's decoded RGB **only after** composition. Flattened at export to avoid per-tile PDF resampling seams. |
| `reconstruction.pdf` | **Edit the evidence placement.** All 15 frame images and 46 original word images are separate PDF objects. Tiny, near-white JPEG ringing is intentionally omitted in this branch. |
| `vectors.pdf` | Fifteen true frames and 46 separate vector word outlines traced at subpixel resolution. Does not pretend the author had editable PDF labels. |
| `native.pdf` | Fifteen frames and newly typeset, selectable PDF text. Default is embedded oblique sans; `--font /path/to/italic.ttf` overrides the substitute. This is not an identification of the author’s typeface. |
| `layout.json`, `frames/`, `words/`, `paper-matte.npz`, `receipt.json` | Editable inventories, locally derived evidence, tiny near-white compression residues, and per-branch QA. Do not put author images or proof PDFs in the public repository. |

**Reuse without opening the paper again.** Edit a copy of the layout with its assets, swap frames and change `labels[].text` and `ink_box_px`, then run:

```sh
python3 cases/cvpr26_video_pairs/rapid/build.py --template path/to/layout.json --out /path/to/new-case
```

This produces newly typeset `custom.pdf`; frames must already match the selected crop aspect. `--style faithful` instead replays the printed word patches without re-typesetting. Do not use faithful mode for a changed label. Author-traced glyphs are not a general-purpose font. For different content, use your own frames, score sources, case ID and prompt; do not carry the RAPID measurements forward.

**Acceptance:** the pinned source must match in SHA, image dimensions and PDF bbox. All 15 published slots have fixed RGB hashes and placement tolerance <0.001 pt. The sparse residual is constrained to under 2% of pixels with every RGB channel ≥240 (it cannot carry a frame or any legible ink). The native-size proof must have zero differing RGB pixels. The receipt compares both device renderings: the embedded JPEG and the lossless proof can take different decoding paths at lower DPI; do not represent the editable PDF's tile-resampling error as a change in the frames. Run `pdftoppm` for independent Poppler evidence; absence is explicitly marked.

**Metric audit:** three rounded latency annotations (66/43/37 min) correspond to the 3971/2601/2221 s Wan2.1-14B rows of [Table 1, p. 7](https://openaccess.thecvf.com/content/CVPR2026/papers/Lin_RAPID_Reusing_Attention_Sparsity_with_Inter-step_Adaptation_for_Efficient_Video_CVPR_2026_paper.pdf#page=7). The 26.11/22.61 PSNR and 1.53x/1.79x figures are benchmark summaries, not scores measured on the astronaut clip.
