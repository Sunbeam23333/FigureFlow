"""Offline fixture: editing one component must not leak into other frame/time slots."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from PIL import Image

spec = importlib.util.spec_from_file_location("rapid_fig1_renderer", Path(__file__).with_name("build.py"))
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_frame_replacement_is_local_and_matte_cannot_hide_a_picture(tmp_path):
    layout = {"size_px": [120, 60], "size_pt": [120, 60],
              "frames": [{"file": "a.png", "place_px": [0, 10, 50, 50]},
                         {"file": "b.png", "place_px": [60, 10, 110, 50]}],
              "labels": [], "matte": {"file": "matte.npz", "count": 1}}
    np.savez_compressed(tmp_path / "matte.npz", indices=np.array([0]), colors=np.array([[251, 254, 255]]))
    for tile in ["a.png", "b.png"]:
        Image.new("RGB", (50, 40), (130, 140, 160)).save(tmp_path / tile)
    first = renderer.faithful(layout, tmp_path, tmp_path / "before.pdf")
    Image.new("RGB", (50, 40), (15, 112, 60)).save(tmp_path / "b.png")
    second = renderer.faithful(layout, tmp_path, tmp_path / "after.pdf")
    changed = (second != first).any(2)
    assert changed.sum() == 50 * 40
    assert changed[10:50, 60:110].all()
    np.savez_compressed(tmp_path / "matte.npz", indices=np.array([0]), colors=np.array([[0, 0, 0]]))
    with pytest.raises(ValueError, match="evidence boundary"):
        renderer.faithful(layout, tmp_path, tmp_path / "invalid.pdf")


def test_native_revision_retypesets_new_word_in_visible_pdf(tmp_path):
    layout = {"size_px": [100, 50], "size_pt": [100, 50], "frames": [],
              "palette": {"ink": "#000000"}, "labels": [
                  {"text": "Updated", "ink": "ink", "ink_box_px": [10, 5, 68, 28]}]}
    renderer.compose(layout, tmp_path, tmp_path / "updated.pdf")
    with pymupdf.open(tmp_path / "updated.pdf") as d:
        assert d[0].get_text().strip() == "Updated"
        assert d[0].get_texttrace()[0]["type"] == 0  # filled visible vector text, not an OCR overlay
        assert d[0].get_image_info() == []


def test_pinned_recipe_keeps_shown_slots_and_table_scope():
    recipe = json.loads(renderer.RECIPE.read_text())
    slots = [h for row in recipe["rows"] for h in row["rgb_sha256"]]
    assert len(slots) == len(set(slots)) == 15
    assert [row["table1"]["latency_s"] for row in recipe["rows"]] == [3971, 2601, 2221]
    assert "Not per-frame" in recipe["metric_scope"]
    assert recipe["columns_px"][0] == [0, 402]
