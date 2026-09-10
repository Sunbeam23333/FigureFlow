from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from demo_core.context_bundle import ContextBundle
from demo_core.research_harness import ResearchHarness


class ContextTests(unittest.TestCase):
    def test_full_source_is_preserved_and_budget_never_truncates(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.txt"
            source.write_text("BEGIN " + "evidence " * 5000 + " END")
            context = ContextBundle([source])
            self.assertIn("BEGIN", context.full_text())
            self.assertIn(" END", context.full_text())
            self.assertGreater(context.characters, 8000)
            self.assertTrue(context.verify_quote("S1", 1, "BEGIN evidence"))
            with self.assertRaises(ValueError):
                ContextBundle([source], max_characters=30)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "paper.txt"
        self.source.write_text("A learned model predicts future observations from a history and action. SOURCE_END")
        self.fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: None))
        self.harness = ResearchHarness(client=self.fake, sources=[self.source], brief="Draw the mechanism",
            run_dir=self.root / "run", require_exploration=False)

    def tearDown(self):
        self.temp.cleanup()

    def scene(self):
        from demo_core.scene import _font_info
        family = _font_info("Arial", 400)[1]
        return {"canvas": {"width": 1200, "height": 600}, "items": [
            {"id": "heading", "type": "text", "bounds": [40, 40, 1000, 90],
             "text": "Learned dynamics", "font_size": 36, "style": {"font_family": family}}]}

    def test_tool_cannot_read_arbitrary_asset_or_lower_qa(self):
        scene = self.scene()
        scene["qa"] = {"min_font_pt": 0}
        prepared = self.harness._prepare_scene(scene)
        self.assertEqual(prepared["qa"]["min_font_pt"], 7)
        scene["items"].append({"id": "bad", "type": "image", "source": "/etc/passwd", "bounds": [50, 200, 100, 100]})
        with self.assertRaises(ValueError):
            self.harness._prepare_scene(scene)

    def test_measurement_tool_returns_actual_numeric_result(self):
        result, images = self.harness.execute({"tool": "measure_text", "arguments": {
            "text": "World model", "font_size": 28, "font_family": "DejaVu Sans"}})
        self.assertGreater(result["result"]["width"], 100)
        self.assertFalse(images)

    def test_identical_geometry_cannot_fake_six_layouts(self):
        for i in range(6):
            scene = self.scene()
            scene["metadata"] = {"candidate": i}
            self.harness._render({"id": "same", "phase": "rough", "family": f"family{i//2}",
                "density": "compact" if i % 2 == 0 else "spacious", "scene": scene})
        self.assertEqual(len(self.harness.rough_scenes), 1)
        self.assertEqual(len(self.harness.rough_variants), 1)

    def test_claim_bindings_require_known_claims_and_existing_items(self):
        self.harness.design = {"claims": [{"id": "C1"}]}
        scene = self.scene()
        self.assertFalse(self.harness._binding_audit(scene)["pass"])
        scene["metadata"] = {"claim_bindings": {"C1": ["heading"]}}
        self.assertTrue(self.harness._binding_audit(scene)["pass"])
        scene["metadata"]["claim_bindings"] = {"invented": ["heading"]}
        self.assertFalse(self.harness._binding_audit(scene)["pass"])

    def test_invalid_review_or_error_cannot_pass(self):
        scene = self.scene()
        self.harness.design = {"claims": [{"id": "C1"}]}
        scene["metadata"] = {"claim_bindings": {"C1": ["heading"]}}
        self.harness._render({"id": "candidate", "scene": scene})
        def review(**kw):
            return {"model": "gpt-5.6-sol", "output_text": json.dumps({"pass": True,
                "issues": [{"severity": "error", "description": "Unreadable", "fix": "Increase size"}]})}
        self.harness.gateway.client.responses.create = review
        result, _ = self.harness._independent_review({"id": "candidate"})
        self.assertFalse(result["pass"])

    def test_record_design_rejects_incomplete_brief(self):
        result, _ = self.harness.execute({"tool": "record_design", "arguments": {"design": {
            "takeaway": "future model", "claims": [{"id": "C1", "source_id": "S1", "page": 1,
            "quote": "A learned model"}]}}})
        self.assertIn("error", result["result"])

    def test_disabled_asset_tool_is_actionable_not_silent_fallback(self):
        result, images = self.harness.execute({"tool": "generate_icon", "arguments": {
            "id": "new_icon", "meaning": "robot gripper"}})
        self.assertEqual(result["result"]["error"], "ResearchAssetError")
        self.assertFalse(images)
        self.assertFalse(self.harness.assets)

    def test_asset_generation_receives_complete_context_and_registers_pixels(self):
        from PIL import Image
        captured = []
        path = self.harness.run_dir / "new.png"
        Image.new("RGB", (128, 128), "blue").save(path)
        def generate(asset_id, meaning, context):
            captured.append(context)
            return {"id": asset_id, "meaning": meaning, "kind": "generated_illustration", "path": str(path)}
        self.harness.asset_tools.generate_icon = generate
        result, images = self.harness.execute({"tool": "generate_icon", "arguments": {
            "id": "new_icon", "meaning": "robot gripper"}})
        self.assertIn("SOURCE_END", json.dumps(captured[0]))
        self.assertIn("current_design", json.dumps(captured[0]))
        self.assertEqual(result["result"]["id"], "new_icon")
        self.assertTrue(images)
        self.assertIn("new_icon", self.harness.assets)
        self.assertNotIn(str(self.harness.run_dir), json.dumps(result))

    def test_real_reference_credit_cannot_be_omitted_by_scene(self):
        from PIL import Image
        path = self.harness.run_dir / "photo.png"
        Image.new("RGB", (128, 128), "blue").save(path)
        self.harness._register_asset({"id": "photo", "path": str(path), "kind": "validated-public-reference",
            "provenance": {"provider": "wikimedia-commons", "title": "Robot", "author": "A. Author",
                           "license_name": "CC BY 4.0"}})
        scene = self.scene()
        scene["items"].append({"id": "photo_item", "type": "image", "source": "asset:photo",
                              "bounds": [50, 200, 200, 200]})
        prepared = self.harness._prepare_scene(scene)
        footer = prepared["items"][-1]
        self.assertIn("A. Author", footer["text"])
        self.assertIn("CC BY 4.0", footer["text"])
        self.assertGreater(prepared["canvas"]["height"], scene["canvas"]["height"])

    def test_scoped_revision_preserves_locked_items_and_canvas(self):
        from copy import deepcopy
        scene = self.scene()
        scene["items"].append({"id": "locked", "type": "shape", "bounds": [50, 200, 100, 100]})
        self.harness.revision_base = deepcopy(scene)
        self.harness.editable_ids = {"heading"}
        edited = deepcopy(scene)
        edited["items"][0]["text"] = "Revised title"
        self.harness._prepare_scene(edited)
        edited["items"][1]["bounds"][0] = 80
        with self.assertRaises(ValueError):
            self.harness._prepare_scene(edited)
        edited = deepcopy(scene)
        edited["canvas"]["width"] += 1
        with self.assertRaises(ValueError):
            self.harness._prepare_scene(edited)

    def test_packaged_scene_seed_maps_only_manifest_asset_and_keeps_credit_idempotent(self):
        from PIL import Image
        photo = self.harness.run_dir / "photo.jpg"
        Image.new("RGB", (128, 128), "blue").save(photo)
        record = {"id": "photo", "path": str(photo), "kind": "validated-public-reference",
                  "provenance": {"provider": "wikimedia-commons", "title": "Robot",
                                 "author": "A. Author", "license_name": "CC BY 4.0"}}
        self.harness._register_asset(record)
        scene = self.scene()
        scene["items"].append({"id": "photo_item", "type": "image", "source": "asset:photo",
                               "bounds": [50, 200, 200, 200]})
        packaged = self.harness._prepare_scene(scene)
        packaged["items"][-2]["source"] = "assets/photo.jpg"
        revised = ResearchHarness(client=self.fake, sources=[self.source], brief="Repair title",
            run_dir=self.root / "revision", assets=[record], initial_scene=packaged,
            initial_design=None, editable_ids=["heading"], require_exploration=False)
        self.assertEqual(revised.revision_base["items"][-2]["source"], "asset:photo")
        self.assertIsNotNone(revised.seed_scene_sha256)
        context_manifest = json.loads((revised.run_dir / "context_manifest.json").read_text())
        self.assertEqual(context_manifest["revision"]["seed_scene_sha256"], revised.seed_scene_sha256)
        self.assertEqual(context_manifest["revision"]["editable_ids"], ["heading"])
        prepared = revised._prepare_scene(revised.revision_base)
        self.assertEqual(prepared["canvas"], revised.revision_base["canvas"])
        self.assertEqual([item["id"] for item in prepared["items"]],
                         [item["id"] for item in revised.revision_base["items"]])
        self.assertEqual(sum(item["id"] == "ff_credit_footer" for item in prepared["items"]), 1)
        bad = self.scene()
        bad["items"].append({"id": "bad_image", "type": "image",
                             "source": "assets/not-in-manifest.jpg", "bounds": [50, 200, 100, 100]})
        with self.assertRaises(ValueError):
            revised._normalize_seed_scene(bad)

    def test_delivery_zip_preserves_raw_asset_extension(self):
        from PIL import Image
        photo = self.harness.run_dir / "assets" / "photo.jpg"
        Image.new("RGB", (128, 128), "blue").save(photo)
        self.harness.assets["photo"] = {"id": "photo", "path": photo, "raw_path": str(photo)}
        scene = self.scene()
        scene["metadata"] = {"claim_bindings": {"C1": ["heading"]}}
        self.harness.design = {"claims": [{"id": "C1"}]}
        self.harness.design_audit = {"pass": True}
        (self.harness.run_dir / "design.json").write_text(json.dumps(self.harness.design))
        self.harness.candidates["candidate"] = {"scene": scene, "scene_hash": "hash",
            "output": {"qa": {"ok": True}}, "stem": str(self.harness.run_dir / "candidate")}
        self.harness.reviews["candidate"] = {"pass": True, "scene_hash": "hash"}
        self.harness.gateway.records = [{"status": "completed", "identity_status": "reported_match"}]
        self.harness.gateway.pinned_reported_model = "gpt-5.6-sol"

        def fake_render(unused_scene, stem, **kwargs):
            for suffix in (".svg", ".png", ".pdf"):
                Path(str(stem) + suffix).write_bytes(b"artifact")
            return {"qa": {"ok": True}}

        completed = SimpleNamespace(stdout=json.dumps({"ok": True, "summary": {"warnings": []}}))
        with patch("demo_core.scene.render_scene", fake_render), \
             patch("demo_core.research_harness.subprocess.run", return_value=completed):
            result, _ = self.harness._finish({"id": "candidate"})
        self.assertEqual(result["status"], "automated_review_passed")
        with zipfile.ZipFile(self.harness.run_dir / "delivery.zip") as package:
            self.assertIn("asset_sources/photo.jpg", package.namelist())
            self.assertNotIn("asset_sources/photo.png", package.namelist())
            self.assertNotIn("context_manifest.json", package.namelist())
        manifest = json.loads((self.harness.run_dir / "manifest.json").read_text())
        self.assertEqual(manifest["run_mode"], "fresh")
        self.assertIsNone(manifest["revision"]["seed_scene_sha256"])

    def test_render_error_is_repairable_and_review_is_invalidated(self):
        args = {"id": "candidate", "phase": "refined", "family": "custom", "scene": self.scene()}
        first, _ = self.harness.execute({"tool": "render", "arguments": args})
        self.assertTrue(first["result"]["qa"]["ok"])
        self.harness.reviews["candidate"] = {"pass": True, "scene_hash": first["result"]["scene_hash"]}
        repaired, _ = self.harness.execute({"tool": "patch_scene", "arguments": {"id": "candidate",
            "updates": [{"id": "heading", "text": "Updated learned dynamics"}]}})
        self.assertNotIn("candidate", self.harness.reviews)
        self.assertNotEqual(first["result"]["scene_hash"], repaired["result"]["scene_hash"])
        outcome, _ = self.harness.execute({"tool": "finish", "arguments": {"id": "candidate"}})
        self.assertEqual(outcome["result"]["error"], "not_ready")
        self.assertFalse((self.harness.run_dir / "delivery.zip").exists())

    def test_patch_receipt_replays_style_edit_and_protects_unchanged_objects(self):
        from demo_core.scene_patch import apply_scene_patch, hash_scene
        scene = self.scene()
        scene["items"].append({"id": "locked", "type": "shape", "bounds": [50, 200, 100, 100]})
        self.harness._render({"id": "candidate", "scene": scene})
        outcome, _ = self.harness.execute({"tool": "patch_scene", "arguments": {"id": "candidate",
            "base_sha256": hash_scene(scene), "scope": {"editable_ids": ["heading"]},
            "updates": [{"id": "heading", "text": "Revised dynamics", "style": {"fill": "#123456"}}]}})
        receipt = outcome["result"]["patch_receipt"]
        self.assertEqual(receipt["changed_ids"], ["heading"])
        self.assertEqual(receipt["unchanged_ids"], ["locked"])
        entry = self.harness.candidates["candidate"]["patch_history"][0]
        base = json.loads((self.harness.run_dir / entry["base_file"]).read_text())
        patch_data = json.loads((self.harness.run_dir / entry["patch_file"]).read_text())
        replayed, _ = apply_scene_patch(base, patch_data)
        self.assertEqual(replayed, self.harness.candidates["candidate"]["scene"])
        self.assertEqual(replayed["items"][0]["style"]["font_family"], scene["items"][0]["style"]["font_family"])

    def test_stale_or_duplicate_patch_does_not_replace_candidate_or_review(self):
        from copy import deepcopy
        scene = self.scene()
        self.harness._render({"id": "candidate", "scene": scene})
        original = deepcopy(self.harness.candidates["candidate"])
        self.harness.reviews["candidate"] = {"pass": True, "scene_hash": original["scene_hash"]}
        for changes in ({"base_sha256": "0" * 64, "updates": [{"id": "heading", "text": "No"}]},
                        {"updates": [{"id": "heading", "text": "First"}, {"id": "heading", "text": "Second"}]}):
            result, _ = self.harness.execute({"tool": "patch_scene", "arguments": {"id": "candidate", **changes}})
            self.assertIn("error", result["result"])
            self.assertEqual(self.harness.candidates["candidate"], original)
            self.assertIn("candidate", self.harness.reviews)

    def test_saved_patch_tampering_blocks_finish_and_replay_chain_is_contiguous(self):
        scene = self.scene()
        self.harness._render({"id": "candidate", "scene": scene})
        for text in ("First revision", "Second revision"):
            self.harness.execute({"tool": "patch_scene", "arguments": {"id": "candidate",
                "updates": [{"id": "heading", "text": text}]}})
        candidate = self.harness.candidates["candidate"]
        self.assertEqual(self.harness._verify_patch_history(candidate), {"pass": True, "patch_count": 2})
        entry = candidate["patch_history"][0]
        patch_file = self.harness.run_dir / entry["patch_file"]
        patch_data = json.loads(patch_file.read_text())
        patch_data["updates"][0]["text"] = "Tampered revision"
        patch_file.write_text(json.dumps(patch_data))
        with self.assertRaises(ValueError):
            self.harness._verify_patch_history(candidate)
        result, _ = self.harness._finish({"id": "candidate"})
        self.assertEqual(result["error"], "not_ready")
        self.assertIn("Saved replay patch", json.dumps(result["unmet"]))
        self.assertFalse((self.harness.run_dir / "delivery.zip").exists())

    def test_patch_cannot_widen_caller_revision_scope(self):
        from copy import deepcopy
        scene = self.scene()
        scene["items"].append({"id": "locked", "type": "shape", "bounds": [50, 200, 100, 100]})
        self.harness.revision_base = deepcopy(scene)
        self.harness.editable_ids = {"heading"}
        self.harness._render({"id": "candidate", "scene": scene})
        result, _ = self.harness.execute({"tool": "patch_scene", "arguments": {"id": "candidate",
            "scope": {"editable_ids": ["heading", "locked"]}, "updates": [{"id": "locked", "bounds": [70, 200, 100, 100]}]}})
        self.assertIn("error", result["result"])
        self.assertEqual(self.harness.candidates["candidate"]["scene"], scene)

    def test_post_patch_qa_failure_stays_a_draft_and_invalidates_review(self):
        scene = self.scene()
        first, _ = self.harness._render({"id": "candidate", "scene": scene})
        self.harness.reviews["candidate"] = {"pass": True, "scene_hash": first["scene_hash"]}
        result, _ = self.harness.execute({"tool": "patch_scene", "arguments": {"id": "candidate",
            "updates": [{"id": "heading", "font_size": 200}]}})
        self.assertFalse(result["result"]["qa"]["ok"])
        self.assertEqual(result["result"]["patch_receipt"]["qa_status"], "draft_only_post_render_qa_failed")
        self.assertNotIn("candidate", self.harness.reviews)
        finished, _ = self.harness.execute({"tool": "finish", "arguments": {"id": "candidate"}})
        self.assertEqual(finished["result"]["error"], "not_ready")
        self.assertFalse((self.harness.run_dir / "delivery.zip").exists())

    def test_symbol_declarations_fail_qa_without_claiming_semantic_truth(self):
        scene = self.scene()
        scene["items"].extend([
            {"id": "first", "type": "shape", "shape": "ellipse", "bounds": [50, 200, 100, 100]},
            {"id": "second", "type": "shape", "shape": "rect", "bounds": [300, 200, 100, 100]},
        ])
        scene["metadata"] = {"symbol_registry": {"tag": {"kind": "tag-set", "shape": "ellipse"}},
                             "concept_bindings": {"first": "tag", "second": "tag"}}
        result, _ = self.harness._render({"id": "candidate", "scene": scene})
        self.assertFalse(result["qa"]["ok"])
        self.assertFalse(result["qa"]["symbol_consistency"]["pass"])
        self.assertIn("No semantic truth", result["qa"]["symbol_consistency"]["scope"])

    def test_svg_source_is_retained_and_model_receives_only_png_preview(self):
        source = self.root / "mark.svg"
        payload = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="24" fill="#336699"/></svg>'
        source.write_bytes(payload)
        asset = {"id": "mark", "path": str(source), "kind": "official-brand", "meaning": "A test brand mark",
                 "provenance": {"source_page": "https://example.org/brand"}}
        harness = ResearchHarness(client=self.fake, sources=[self.source], brief="Use a supplied mark",
            run_dir=self.root / "svg-run", assets=[asset], require_exploration=False)
        self.assertEqual(harness.assets["mark"]["path"].read_bytes(), payload)
        self.assertEqual(harness.assets["mark"]["path"].suffix, ".svg")
        self.assertEqual(harness.images["mark"].suffix, ".png")
        image_entries = [item for item in harness.initial_content if item.get("type") == "input_image"]
        self.assertEqual(len(image_entries), 1)
        self.assertTrue(image_entries[0]["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(harness.assets["mark"]["provenance"], asset["provenance"])
        scene = self.scene()
        scene["items"].append({"id": "mark_item", "type": "image", "source": "asset:mark", "bounds": [50, 200, 100, 100]})
        prepared = harness._prepare_scene(scene)
        self.assertTrue(prepared["items"][-1]["source"].endswith("mark.svg"))

    def test_runtime_svg_preview_is_derived_from_source_not_untrusted_preview(self):
        from PIL import Image
        source = self.harness.run_dir / "mark.svg"
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#0000FF"/></svg>')
        wrong = self.harness.run_dir / "wrong.png"
        Image.new("RGB", (32, 32), "red").save(wrong)
        result, images = self.harness._register_asset({"id": "mark", "path": str(source), "raw_path": str(source),
            "preview_path": str(wrong), "kind": "official-brand"})
        self.assertEqual(result["media_kind"], "svg-vector")
        self.assertTrue(all(image.suffix == ".png" for image in images))
        with Image.open(self.harness.images["mark"]) as preview:
            self.assertEqual(preview.convert("RGB").getpixel((preview.width // 2, preview.height // 2)), (0, 0, 255))
        outcome, _ = self.harness.execute({"tool": "process_asset", "arguments": {"asset_id": "mark", "new_id": "matte"}})
        self.assertIn("error", outcome["result"])

    def test_delivery_includes_replay_patch_without_local_context_logs(self):
        scene = self.scene()
        scene["metadata"] = {"claim_bindings": {"C1": ["heading"]}}
        self.harness.design = {"claims": [{"id": "C1"}]}
        self.harness.design_audit = {"pass": True}
        (self.harness.run_dir / "design.json").write_text(json.dumps(self.harness.design))
        self.harness._render({"id": "candidate", "scene": scene})
        self.harness.execute({"tool": "patch_scene", "arguments": {"id": "candidate", "updates": [{"id": "heading", "text": "New dynamics"}]}})
        candidate = self.harness.candidates["candidate"]
        self.harness.reviews["candidate"] = {"pass": True, "scene_hash": candidate["scene_hash"]}
        self.harness.gateway.records = [{"status": "completed", "identity_status": "reported_match"}]
        self.harness.gateway.pinned_reported_model = "gpt-5.6-sol"
        def fake_render(unused_scene, stem, **kwargs):
            for suffix in (".svg", ".png", ".pdf"):
                Path(str(stem) + suffix).write_bytes(b"artifact")
            return {"qa": {"ok": True}}
        completed = SimpleNamespace(stdout=json.dumps({"ok": True, "summary": {"warnings": []}}))
        with patch("demo_core.scene.render_scene", fake_render), patch("demo_core.research_harness.subprocess.run", return_value=completed):
            outcome, _ = self.harness._finish({"id": "candidate"})
        self.assertEqual(outcome["status"], "automated_review_passed")
        with zipfile.ZipFile(self.harness.run_dir / "delivery.zip") as archive:
            for key in ("base_file", "patch_file", "receipt_file"):
                self.assertIn(candidate["patch_history"][0][key], archive.namelist())
            self.assertNotIn("events.json", archive.namelist())
            self.assertNotIn("model_calls.jsonl", archive.namelist())

    def test_source_and_output_history_survive_successive_model_turns(self):
        calls = []
        def create(**kw):
            calls.append(kw)
            text = json.dumps({"summary": "Check evidence", "actions": [
                {"tool": "search_source", "arguments": {"query": "future"}}]})
            return {"model": "gpt-5.6-sol", "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": text}]}]}
        self.harness.gateway.client.responses.create = create
        self.harness.gateway.max_calls = 2
        outcome = self.harness.run()
        self.assertEqual(outcome["status"], "draft_only")
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertIn("SOURCE_END", json.dumps(call["input"]))
            self.assertEqual(call["model"], "gpt-5.6-sol")
            self.assertEqual(call["reasoning"], {"effort": "medium"})
        self.assertTrue(any(item.get("role") == "assistant" for item in calls[1]["input"]))

    def scripted_client(self, harness, answers):
        calls = []

        def create(**kwargs):
            calls.append(json.loads(json.dumps(kwargs)))
            text = json.dumps(answers[min(len(calls) - 1, len(answers) - 1)])
            return {"model": "gpt-5.6-sol", "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": text}]}]}

        harness.gateway.client = SimpleNamespace(responses=SimpleNamespace(create=create))
        return calls

    def test_oversized_batch_executes_nothing_then_accepts_corrected_turn(self):
        action = {"tool": "search_source", "arguments": {"query": "future"}}
        calls = self.scripted_client(self.harness, [
            {"summary": "Read evidence", "actions": [action] * 13},
            {"summary": "Split batch", "actions": [action]},
        ])
        self.harness.gateway.max_calls = 2
        original_seconds = self.harness.max_seconds
        outcome = self.harness.run()
        self.assertEqual(outcome["stop_reason"], "ModelCallLimitError")
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.harness.gateway.max_calls, 2)
        self.assertEqual(self.harness.max_seconds, original_seconds)
        events = self.harness.events
        self.assertEqual([event["tool"] for event in events],
                         ["agent_turn", "action_batch_validation", "agent_turn", "search_source"])
        self.assertEqual(events[1]["result"]["executed_actions"], 0)
        self.assertIn("received 13", events[1]["result"]["detail"])
        self.assertIn("invalid_action_batch", json.dumps(calls[1]["input"]))
        self.assertIn("SOURCE_END", json.dumps(calls[1]["input"]))
        self.assertEqual(len(json.loads((self.harness.run_dir / "turns/001.json").read_text())["actions"]), 13)
        self.assertIn("1-12 actions per response", self.harness.instructions)

    def test_malformed_batches_never_partially_execute_or_extend_call_budget(self):
        action = {"tool": "search_source", "arguments": {"query": "future"}}
        invalid = [None, [], "not an object", {}, {"actions": []},
                   {"actions": "search_source"}, {"actions": {}}, {"actions": [None]},
                   {"actions": ["search_source"]}, {"actions": [{}]},
                   {"actions": [{"tool": 1, "arguments": {}}]},
                   {"actions": [{"tool": " ", "arguments": {}}]},
                   {"actions": [{"tool": "search_source"}]},
                   {"actions": [{"tool": "search_source", "arguments": []}]},
                   {"actions": [action, {"tool": "search_source", "arguments": None}]}]
        for index, answer in enumerate(invalid):
            with self.subTest(answer=answer):
                harness = ResearchHarness(client=self.fake, sources=[self.source], brief="Draw mechanism",
                    run_dir=self.root / f"invalid-{index}", max_calls=2, require_exploration=False)
                calls = self.scripted_client(harness, [answer])
                with patch.object(harness, "execute", wraps=harness.execute) as execute:
                    outcome = harness.run()
                self.assertEqual(outcome["status"], "draft_only")
                self.assertEqual(outcome["stop_reason"], "ModelCallLimitError")
                self.assertEqual(len(calls), 2)
                self.assertEqual(outcome["calls"], 2)
                execute.assert_not_called()
                errors = [event for event in harness.events if event["tool"] == "action_batch_validation"]
                self.assertEqual(len(errors), 2)
                self.assertTrue(all(event["result"]["executed_actions"] == 0 for event in errors))
                self.assertFalse((harness.run_dir / "delivery.zip").exists())

    def test_invalid_batch_does_not_reset_elapsed_time_budget(self):
        calls = self.scripted_client(self.harness, [{"actions": []}])
        original_create = self.harness.gateway.client.responses.create
        original_seconds = self.harness.max_seconds

        def expired_during_response(**kwargs):
            answer = original_create(**kwargs)
            self.harness.started -= original_seconds + 1
            return answer

        self.harness.gateway.client.responses.create = expired_during_response
        outcome = self.harness.run()
        self.assertEqual(outcome["stop_reason"], "time_budget")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.harness.max_seconds, original_seconds)
        self.assertFalse((self.harness.run_dir / "delivery.zip").exists())

    def test_direct_execute_malformed_action_returns_error_instead_of_unpacking(self):
        for action in [None, [], "tool", {}, {"tool": None, "arguments": {}},
                       {"tool": "search_source", "arguments": "future"}]:
            with self.subTest(action=action):
                result, images = self.harness.execute(action)
                self.assertEqual(result["tool"], "invalid_action")
                self.assertEqual(result["result"]["error"], "ValueError")
                self.assertFalse(images)


if __name__ == "__main__":
    unittest.main()
