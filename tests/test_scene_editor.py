import json
from pathlib import Path
from unittest.mock import patch

import pytest

from demo_core.scene_editor import edit_scene_file
from demo_core.scene_patch import hash_scene, ScenePatchError


def fixture_scene(root):
    assets = root / "assets"
    assets.mkdir()
    for name, color in (("a", "#0055AA"), ("b", "#008877")):
        (assets / f"{name}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="20" r="15" fill="{color}"/></svg>')
    scene = {"canvas": {"width": 400, "height": 200}, "items": [
        {"id": "logo", "type": "image", "source": "assets/a.svg", "bounds": [20, 40, 60, 60]},
        {"id": "fixed", "type": "shape", "shape": "rect", "bounds": [160, 40, 100, 60], "style": {"fill": "#FFFFFF", "stroke": "#222222"}}]}
    path = root / "scene.json"
    path.write_text(json.dumps(scene))
    return path, scene


def test_edit_is_portable_replayable_and_preserves_unrelated_items(tmp_path):
    source, scene = fixture_scene(tmp_path)
    edit = {"base_sha256": hash_scene(scene), "scope": {"editable_ids": ["logo"]},
            "updates": [{"id": "logo", "source": "assets/b.svg"}]}
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(edit))
    result = edit_scene_file(source, tmp_path / "out", patch_file=patch_path)
    assert result["human_approval"] == "pending"
    assert result["geometry_qa"]["ok"]
    for name in ("figure.svg", "figure.pdf", "figure.png", "edit.receipt.json", "assets/a.svg", "assets/b.svg"):
        assert (tmp_path / "out" / name).is_file()
    updated = json.loads((tmp_path / "out/figure.scene.json").read_text())
    assert updated["items"][1] == scene["items"][1]
    replay = edit_scene_file(tmp_path / "out/before.scene.json", tmp_path / "replay", patch_file=tmp_path / "out/edit.patch.json")
    assert replay["after_sha256"] == result["after_sha256"]
    assert (tmp_path / "out/figure.svg").read_bytes() == (tmp_path / "replay/figure.svg").read_bytes()


def test_stale_hash_does_not_create_output(tmp_path):
    source, scene = fixture_scene(tmp_path)
    edit = tmp_path / "patch.json"
    edit.write_text(json.dumps({"base_sha256": "0" * 64, "updates": [{"id": "logo", "source": "assets/b.svg"}]}))
    with pytest.raises(ScenePatchError):
        edit_scene_file(source, tmp_path / "out", patch_file=edit)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name", ["../a.svg", "/etc/passwd", "assets/../../a.svg", "figure.scene.json"])
def test_portable_import_rejects_unregistered_paths(tmp_path, name):
    source, scene = fixture_scene(tmp_path)
    scene["items"][0]["source"] = name
    source.write_text(json.dumps(scene))
    with pytest.raises((ValueError, FileNotFoundError)):
        edit_scene_file(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_does_not_overwrite_output(tmp_path):
    source, scene = fixture_scene(tmp_path)
    (tmp_path / "out").mkdir()
    with pytest.raises(FileExistsError):
        edit_scene_file(source, tmp_path / "out")
