# Replayable local edit

The two marks are original fictional shapes created for this MIT-licensed
synthetic example. They are not real brands or AI performance evidence.

From the repository root:

```bash
python -m demo_core.scene_editor edit examples/scoped_edit/before.scene.json \
  --patch examples/scoped_edit/edit.patch.json --output demo/output/scoped-edit
```

Only `source_mark` and `source_label` change. The remaining nine objects, canvas
and reading order stay unchanged and are included in the integrity receipt.
Open the SVG/PNG, inspect the receipt, then repeat the patch from the generated
`before.scene.json` into a fresh directory to verify portable replay.

If Arial is unavailable, inspect the font substitution warning. For a new
scene choose a family returned by `demo_core.scene.font_environment()`, then
make a new patch hash; never reuse a stale patch hash after changing fonts.
