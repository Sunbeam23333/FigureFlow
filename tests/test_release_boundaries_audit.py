"""Independent, fully offline boundary regression tests for release adapters."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw
import pytest

from demo_core.official_assets import CATALOG, OfficialAssetError, import_official, search_official
from demo_core.reference_import import DownloadPayload
from demo_core.research_harness import ResearchHarness
from demo_core.scene_editor import edit_scene_file
from demo_core.scene_patch import apply_scene_patch, hash_scene


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("An offline boundary test attempted a network connection")
    monkeypatch.setattr("socket.socket.connect", fail)


def test_official_catalog_viewport_svg_round_trips_its_own_sanitizer(tmp_path):
    raw = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 93 80"><rect x="5" y="5" width="80" height="30" fill="#00AACC"/></svg>'
    bilibili = next(item for item in CATALOG if item.id == "official-bilibili")
    fixture = replace(bilibili, sha256=hashlib.sha256(raw).hexdigest())
    def transport(url, timeout, size):
        return DownloadPayload(raw, "image/svg+xml", url, len(raw))
    with patch("demo_core.official_assets.CATALOG", (fixture,)):
        result = import_official(fixture.id, tmp_path, transport=transport)
    assert Path(result["raw_path"]).read_bytes() == raw
    assert Path(result["preview_path"]).is_file()
    with Image.open(result["preview_path"]) as preview:
        assert preview.width / preview.height == pytest.approx(93 / 40, abs=0.01)


def test_remote_looking_catalog_queries_and_unknown_ids_cannot_fetch(tmp_path):
    with patch("demo_core.official_assets._fixed_host_download", side_effect=AssertionError("not a catalog ID")):
        assert search_official("https://example.org/qwen.svg") == []
        with pytest.raises(OfficialAssetError):
            import_official("https://example.org/qwen.svg", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_catalog_svg_with_active_content_fails_before_writing(tmp_path):
    raw = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><script>alert(1)</script></svg>'
    gemini = next(item for item in CATALOG if item.id == "official-gemini")
    fixture = replace(gemini, sha256=hashlib.sha256(raw).hexdigest())
    def transport(url, timeout, size):
        return DownloadPayload(raw, "image/svg+xml", url, len(raw))
    with patch("demo_core.official_assets.CATALOG", (fixture,)), pytest.raises(ValueError):
        import_official(fixture.id, tmp_path, transport=transport)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind,provider", [("official-brand", None), ("registered-local-asset", "official-brand")])
def test_official_raster_cannot_enter_generic_background_removal(tmp_path, kind, provider):
    source = tmp_path / "evidence.txt"
    source.write_text("A model encodes text and images independently.")
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: None))
    harness = ResearchHarness(client=fake, sources=[source], brief="Preserve the official mark",
        run_dir=tmp_path / "run", require_exploration=False)
    image = harness.run_dir / "brand.png"
    pixels = Image.new("RGB", (128, 128), "white")
    ImageDraw.Draw(pixels).ellipse((28, 28, 100, 100), fill="#2255AA")
    pixels.save(image)
    harness._register_asset({"id": "brand", "path": str(image), "kind": kind,
        "provenance": {"source_page": "https://example.org/brand", "provider": provider, "processing": "Preserve original artwork"}})
    result, _ = harness.execute({"tool": "process_asset", "arguments": {"asset_id": "brand", "new_id": "modified"}})
    assert "error" in result["result"]
    assert "modified" not in harness.assets


def test_scene_asset_symlink_cannot_escape_explicit_source_directory(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "assets").mkdir()
    outside = tmp_path / "outside.svg"
    outside.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" fill="#00AACC"/></svg>')
    (package / "assets" / "logo.svg").symlink_to(outside)
    scene = {"canvas": {"width": 400, "height": 200}, "items": [
        {"id": "logo", "type": "image", "source": "assets/logo.svg", "bounds": [20, 20, 80, 80]}]}
    source = package / "scene.json"
    source.write_text(json.dumps(scene))
    with pytest.raises(ValueError):
        edit_scene_file(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("fit", ["stretch", "cover"])
@pytest.mark.parametrize("kind,provider", [("official-brand", None), ("user-provided", "official-brand")])
def test_registered_brand_rejects_distorting_or_cropping_layout(tmp_path, fit, kind, provider):
    source = tmp_path / "evidence.txt"
    source.write_text("A model encodes text and images independently.")
    image = tmp_path / "brand.png"
    Image.new("RGBA", (128, 64), "blue").save(image)
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: None))
    harness = ResearchHarness(client=fake, sources=[source], brief="Use the original brand mark",
        run_dir=tmp_path / "run", require_exploration=False,
        assets=[{"id": "brand", "path": str(image), "kind": kind, "provenance": {"provider": provider}}])
    scene = {"canvas": {"width": 600, "height": 400}, "items": [
        {"id": "mark", "type": "image", "source": "asset:brand", "bounds": [30, 30, 150, 150], "fit": fit}]}
    with pytest.raises(ValueError, match="requires contain"):
        harness._prepare_scene(scene)
    scene["items"][0]["fit"] = "contain"
    assert harness._prepare_scene(scene)["items"][0]["source"].endswith("brand.png")


def test_offline_invalid_geometry_is_never_reported_as_passed(tmp_path):
    scene = {"canvas": {"width": 400, "height": 200}, "items": [
        {"id": "box", "type": "shape", "shape": "rect", "bounds": [10, 10, 40, 40], "style": {"fill": "#00AACC"}}]}
    source = tmp_path / "scene.json"
    source.write_text(json.dumps(scene))
    change = {"base_sha256": hash_scene(scene), "updates": [{"id": "box", "bounds": [390, 190, 40, 40]}]}
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(json.dumps(change))
    result = edit_scene_file(source, tmp_path / "out", patch_file=patch_file)
    assert result["geometry_qa"]["ok"] is False
    assert result["human_approval"] == "pending"
    assert result.get("status") not in {"passed", "automated_review_passed"}
    assert result["edit_receipt"]["qa_status"] not in {"passed", "automated_review_passed"}


def test_generated_asset_provider_response_identifier_is_not_in_delivery(tmp_path):
    source = tmp_path / "evidence.txt"
    source.write_text("A model encodes text and images independently.")
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: None))
    harness = ResearchHarness(client=fake, sources=[source], brief="A figure",
        run_dir=tmp_path / "run", require_exploration=False)
    generated = harness.run_dir / "asset.png"
    Image.new("RGB", (64, 64), "blue").save(generated)
    harness._register_asset({"id": "generated", "path": str(generated), "kind": "generated-illustrative-icon",
        "provenance": {"response_id": "fixture-provider-identifier", "requested_model": "gpt-5.6-sol"}})
    scene = {"canvas": {"width": 600, "height": 400}, "items": [
        {"id": "title", "type": "text", "text": "Encoders", "font_size": 30, "bounds": [30, 30, 500, 50]},
        {"id": "icon", "type": "image", "source": "asset:generated", "bounds": [30, 130, 80, 80]}],
        "metadata": {"claim_bindings": {"C1": ["title"]},
            "symbol_registry": {"encoder": {"kind": "encoder", "asset_ref": "asset:generated"}},
            "concept_bindings": {"icon": "encoder"}}}
    harness.design = {"claims": [{"id": "C1"}], "provenance": {"response_id": "fixture-design-identifier"}}
    harness.design_audit = {"pass": True}
    (harness.run_dir / "design.json").write_text(json.dumps(harness.design))
    harness._render({"id": "candidate", "scene": scene})
    changed, _ = harness.execute({"tool": "patch_scene", "arguments": {
        "id": "candidate", "updates": [{"id": "title", "text": "Shared encoders"}]}})
    assert "error" not in changed["result"]
    candidate = harness.candidates["candidate"]
    harness.reviews["candidate"] = {"pass": True, "scene_hash": candidate["scene_hash"]}
    harness.gateway.records = [{"status": "completed", "identity_status": "reported_match",
        "response_id": "fixture-call-identifier", "nested": [{"response_id": "fixture-nested-identifier"}]}]
    harness.gateway.pinned_reported_model = "gpt-5.6-sol"
    def fake_render(unused_scene, stem, **kwargs):
        for suffix in (".svg", ".png", ".pdf"):
            Path(str(stem) + suffix).write_bytes(b"artifact")
        return {"qa": {"ok": True}}
    completed = SimpleNamespace(stdout=json.dumps({"ok": True, "summary": {"warnings": []}}))
    with patch("demo_core.scene.render_scene", fake_render), patch("demo_core.research_harness.subprocess.run", return_value=completed):
        outcome, _ = harness._finish({"id": "candidate"})
    assert outcome["status"] == "automated_review_passed"
    manifest = json.loads((harness.run_dir / "manifest.json").read_text())
    assert "response_id" not in manifest["assets"][0]["provenance"]
    assert harness.assets["generated"]["provenance"]["response_id"] == "fixture-provider-identifier"
    assert harness.gateway.records[0]["response_id"] == "fixture-call-identifier"
    assert "response_id" in json.loads((harness.run_dir / "design.json").read_text())["provenance"]
    with zipfile.ZipFile(harness.run_dir / "delivery.zip") as archive:
        for name in ("manifest.json", "model_audit.json", "design.json"):
            assert "response_id" not in archive.read(name).decode("utf-8")
        entry = manifest["patch_history"][0]
        base = json.loads(archive.read(entry["base_file"]))
        patch_data = json.loads(archive.read(entry["patch_file"]))
        receipt = json.loads(archive.read(entry["receipt_file"]))
        replayed, replay_receipt = apply_scene_patch(base, patch_data)
        assert replayed == candidate["scene"]
        assert replay_receipt["result_sha256"] == receipt["result_sha256"] == candidate["scene_hash"]
        assert base["items"][1]["source"] == "asset:generated"
        assert "response_id" not in json.dumps(base)
        assert "response_id" not in json.dumps(patch_data)
    registration_text = json.dumps(harness.initial_content)
    assert "fixture-provider-identifier" not in registration_text
