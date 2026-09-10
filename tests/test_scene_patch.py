from copy import deepcopy
import math
import unittest

from demo_core.scene_patch import (
    ScenePatchError, apply_scene_patch, hash_scene, validate_symbol_consistency,
)


def scene_fixture():
    return {"version": 1, "canvas": {"width": 800, "height": 500}, "items": [
        {"id": "title", "type": "text", "bounds": [20, 20, 600, 50],
         "text": "Evidence", "font_size": 32,
         "style": {"fill": "#16314D", "font_weight": 700, "font_family": "Arial"}},
        {"id": "card", "type": "shape", "shape": "rect", "bounds": [20, 100, 200, 200],
         "style": {"fill": "#FFFFFF", "stroke": "#123456", "stroke_width": 2}},
        {"id": "flow", "type": "edge", "points": [[220, 200], [400, 200]],
         "style": {"stroke": "#123456", "stroke_width": 3}},
    ]}


class ScenePatchTests(unittest.TestCase):
    def test_hash_is_canonical_and_rejects_nonfinite_or_executable_values(self):
        self.assertEqual(hash_scene({"b": 2, "a": 1}), hash_scene({"a": 1, "b": 2}))
        for invalid in (math.nan, math.inf, -math.inf, lambda: None):
            with self.assertRaises(ScenePatchError):
                hash_scene({"bad": invalid})

    def test_deep_style_merge_and_exact_unchanged_receipt(self):
        base = scene_fixture()
        original = deepcopy(base)
        change = {"base_sha256": hash_scene(base), "updates": [{"id": "title", "text": "Method", "style": {"fill": "#000000"}}]}
        result, receipt = apply_scene_patch(base, change)
        self.assertEqual(base, original)
        self.assertEqual(result["items"][0]["style"], {"fill": "#000000", "font_weight": 700, "font_family": "Arial"})
        self.assertEqual(receipt["changed_ids"], ["title"])
        self.assertEqual(receipt["unchanged_ids"], ["card", "flow"])
        self.assertEqual(receipt["result_sha256"], hash_scene(result))
        self.assertTrue(receipt["canvas_unchanged"])
        for item in original["items"][1:]:
            self.assertEqual(receipt["unchanged_item_sha256"][item["id"]], hash_scene(item))
        self.assertEqual(result, apply_scene_patch(original, deepcopy(change))[0])

    def test_stale_base_fails_without_mutating_inputs(self):
        base = scene_fixture()
        original = deepcopy(base)
        with self.assertRaises(ScenePatchError):
            apply_scene_patch(base, {"base_sha256": "0" * 64, "updates": [{"id": "title", "text": "No"}]})
        self.assertEqual(base, original)

    def test_unknown_ids_duplicates_conflicts_and_duplicate_append_fail_atomically(self):
        for change in (
            {"updates": [{"id": "missing", "text": "No"}]},
            {"updates": [{"id": "title", "text": "First"}, {"id": "title", "text": "Second"}]},
            {"updates": [{"id": "title", "text": "First"}], "remove_ids": ["title"]},
            {"remove_ids": ["title", "title"]},
            {"remove_ids": ["missing"]},
            {"append": [{"id": "title", "type": "shape"}]},
            {"append": [{"id": "new", "type": "shape"}, {"id": "new", "type": "shape"}]},
            {"remove_ids": ["title"], "append": [{"id": "title", "type": "shape"}]},
            {"updates": [{"id": "title", "type": "image"}]},
            {"canvas": {"width": 900}},
        ):
            with self.subTest(change=change):
                base = scene_fixture()
                original = deepcopy(base)
                with self.assertRaises(ScenePatchError):
                    apply_scene_patch(base, {"base_sha256": hash_scene(base), **change})
                self.assertEqual(base, original)

    def test_scope_locks_unselected_items_and_cannot_change_order_or_canvas(self):
        base = scene_fixture()
        scope = {"editable_ids": ["title"]}
        update = {"base_sha256": hash_scene(base), "scope": scope,
                  "updates": [{"id": "title", "text": "New title"}]}
        result, _ = apply_scene_patch(base, update)
        self.assertEqual(result["items"][1:], base["items"][1:])
        self.assertEqual(result["canvas"], base["canvas"])
        for operation in ({"updates": [{"id": "card", "style": {"fill": "#000000"}}]},
                          {"remove_ids": ["title"]},
                          {"append": [{"id": "new", "type": "shape"}]}):
            with self.assertRaises(ScenePatchError):
                apply_scene_patch(base, {"base_sha256": hash_scene(base), "scope": scope, **operation})

    def test_new_items_and_removals_require_explicit_grants_when_scoped(self):
        base = scene_fixture()
        result, receipt = apply_scene_patch(base, {
            "base_sha256": hash_scene(base), "scope": {"editable_ids": ["card"], "allow_remove": True, "allow_append": True},
            "remove_ids": ["card"], "append": [{"id": "new", "type": "shape", "shape": "ellipse", "bounds": [10, 10, 20, 20]}],
        })
        self.assertEqual([item["id"] for item in result["items"]], ["title", "flow", "new"])
        self.assertEqual(receipt["removed_ids"], ["card"])
        self.assertEqual(receipt["added_ids"], ["new"])

    def test_nan_and_malformed_scope_never_escape(self):
        base = scene_fixture()
        for change in ({"updates": [{"id": "title", "font_size": math.nan}]},
                       {"scope": {"editable_ids": ["unknown"]}},
                       {"scope": {"editable_ids": ["title", "title"]}},
                       {"scope": {"allow_append": "true"}},
                       {"remove_ids": None}, {"metadata": None}):
            with self.assertRaises(ScenePatchError):
                apply_scene_patch(base, {"base_sha256": hash_scene(base), **change})

    def test_metadata_replacement_is_audited_without_forcing_legacy_declarations(self):
        base = scene_fixture()
        self.assertEqual(validate_symbol_consistency(base)["checked"], False)
        result, receipt = apply_scene_patch(base, {"base_sha256": hash_scene(base), "metadata": {"status": "illustrative"}})
        self.assertTrue(receipt["metadata_changed"])
        self.assertEqual(result["items"], base["items"])


class SymbolConsistencyTests(unittest.TestCase):
    def scene(self):
        return {"canvas": {"width": 600, "height": 400}, "items": [
            {"id": "one", "type": "image", "source": "asset:tags", "bounds": [10, 10, 80, 80], "style": {"fill": "#123456"}},
            {"id": "two", "type": "image", "source": "asset:tags", "bounds": [200, 10, 80, 80], "style": {"fill": "#654321"}},
        ], "metadata": {"symbol_registry": {"tag": {"kind": "semantic-tag-set", "asset_ref": "asset:tags"}},
                         "concept_bindings": {"one": "tag", "two": "tag"}}}

    def test_repeated_asset_and_branch_colours_are_allowed(self):
        audit = validate_symbol_consistency(self.scene())
        self.assertTrue(audit["pass"])
        self.assertTrue(audit["checked"])
        self.assertIn("No semantic truth", audit["scope"])

    def test_unrelated_asset_cannot_replace_one_repeated_symbol(self):
        base = self.scene()
        before = deepcopy(base)
        with self.assertRaises(ScenePatchError):
            apply_scene_patch(base, {"base_sha256": hash_scene(base), "updates": [{"id": "two", "source": "asset:camera"}]})
        self.assertEqual(base, before)

    def test_coordinated_asset_change_updates_binding_contract(self):
        base = self.scene()
        metadata = deepcopy(base["metadata"])
        metadata["symbol_registry"]["tag"]["asset_ref"] = "asset:new_tags"
        result, _ = apply_scene_patch(base, {"base_sha256": hash_scene(base), "metadata": metadata,
            "updates": [{"id": item, "source": "asset:new_tags"} for item in ["one", "two"]]})
        self.assertTrue(validate_symbol_consistency(result)["pass"])

    def test_unknown_concepts_items_and_missing_canonical_kind_fail(self):
        for mutate in (
            lambda s: s["metadata"]["concept_bindings"].update({"missing": "tag"}),
            lambda s: s["metadata"]["concept_bindings"].update({"one": "missing"}),
            lambda s: s["metadata"]["symbol_registry"]["tag"].pop("kind"),
            lambda s: s["metadata"].pop("concept_bindings"),
        ):
            scene = self.scene()
            mutate(scene)
            self.assertFalse(validate_symbol_consistency(scene)["pass"])

    def test_matching_geometry_with_colour_variants_is_allowed(self):
        scene = self.scene()
        for item in scene["items"]:
            item.update({"type": "shape", "shape": "ellipse"})
            item.pop("source")
        scene["metadata"]["symbol_registry"]["tag"] = {"kind": "tag-set", "shape": "ellipse"}
        self.assertTrue(validate_symbol_consistency(scene)["pass"])
        scene["items"][1]["shape"] = "rect"
        self.assertFalse(validate_symbol_consistency(scene)["pass"])


if __name__ == "__main__":
    unittest.main()
