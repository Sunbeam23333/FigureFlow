from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

from demo_core.scene import SceneError, font_environment, render_scene, render_svg, validate_scene


def example_scene() -> dict:
    return {"version": 1, "canvas": {"width": 600, "height": 320, "include_width_pt": 486},
            "qa": {"margin": 10, "min_font_pt": 6.5}, "items": [
        {"id": "left", "type": "shape", "bounds": [20, 80, 180, 100], "style": {"fill": "#eef6ff"}},
        {"id": "right", "type": "shape", "bounds": [400, 80, 180, 100], "style": {"fill": "#fff7e8"}},
        {"id": "label-left", "type": "text", "bounds": [45, 105, 130, 50], "font_size": 18,
         "text": "Evidence\nledger", "style": {"fill": "#142b4a", "font_weight": 700}},
        {"id": "edge", "type": "edge", "source": "left", "target": "right", "source_port": [200, 130],
         "target_port": [400, 130], "curve": [[200, 130], [270, 50], [330, 210], [400, 130]],
         "style": {"stroke": "#16827a", "stroke_width": 3}},
        {"id": "formula", "type": "formula", "bounds": [230, 235, 140, 35], "text": "x squared",
         "latex": r"x^2 + \sigma", "style": {"fill": "#142b4a"}},
    ]}


class SceneTests(unittest.TestCase):
    def test_render_is_editable_svg_with_curve_text_and_vector_formula(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = render_scene(example_scene(), Path(temporary) / "figure", formats=("svg", "png"))
            self.assertTrue(result["qa"]["ok"])
            svg = Path(result["paths"]["svg"]).read_text()
            ET.fromstring(svg)
            self.assertIn('<text id="label-left"', svg)
            self.assertIn('<svg id="formula"', svg)
            self.assertIn("<path", svg)
            self.assertIn(" C 270.0 50.0 330.0 210.0 400.0 130.0", svg)
            self.assertTrue(Path(result["paths"]["png"]).stat().st_size)

    def test_pdf_uses_declared_paper_width_without_writing_a_real_pdf(self) -> None:
        calls = []
        fake = SimpleNamespace(PDFSurface=SimpleNamespace(convert=lambda **kwargs: calls.append(kwargs)),
                               PNGSurface=SimpleNamespace(convert=lambda **kwargs: None))
        with tempfile.TemporaryDirectory() as temporary, patch.dict("sys.modules", {"cairosvg.surface": fake}):
            render_scene(example_scene(), Path(temporary) / "figure", formats=("pdf",))
        self.assertAlmostEqual(calls[0]["output_width"], 486 * 96 / 72)
        self.assertTrue(callable(calls[0]["url_fetcher"]))
        self.assertFalse(calls[0]["unsafe"])

    def test_font_environment_exposes_names_without_paths(self) -> None:
        environment = font_environment()
        self.assertIn(environment["recommended_family"], environment["available_families"])
        self.assertTrue(all("/" not in family for family in environment["available_families"]))

    def test_explicit_parent_rejects_child_crossing_card_bottom_and_cycles(self) -> None:
        scene = example_scene()
        scene["items"][2]["parent"] = "left"
        scene["items"][2]["bounds"] = [45, 145, 130, 32]
        qa = validate_scene(scene)
        self.assertTrue(any(i["code"] == "child_outside_parent" and i["item"] == "label-left"
                            for i in qa["issues"]))
        nested = example_scene()
        nested["items"][0]["parent"] = "right"
        nested["items"][1]["parent"] = "left"
        with self.assertRaises(SceneError):
            validate_scene(nested)

    def test_parent_must_be_an_existing_shape(self) -> None:
        scene = example_scene(); scene["items"][4]["parent"] = "label-left"
        with self.assertRaises(SceneError):
            validate_scene(scene)

    def test_paints_reject_external_resources_and_css_expressions(self) -> None:
        for unsafe in ("url(https://example.com/x)", "expression(alert(1))", "rgb(999,0,0)"):
            scene = example_scene(); scene["items"][0]["style"]["fill"] = unsafe
            with self.assertRaises(SceneError):
                render_svg(scene)

    def test_data_uri_accepts_verified_raster_and_rejects_embedded_svg(self) -> None:
        import base64
        import io
        buffer = io.BytesIO(); Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
        scene = example_scene()
        scene["items"].append({"id": "inline", "type": "image", "bounds": [250, 20, 20, 20],
                               "source": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()})
        self.assertTrue(validate_scene(scene)["renderable"])
        scene["items"][-1]["source"] = "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode()
        with self.assertRaises(SceneError):
            validate_scene(scene)

    def test_polygon_points_and_edge_bounds_cannot_falsify_geometry(self) -> None:
        scene = example_scene()
        scene["items"].append({"id": "poly", "type": "shape", "shape": "polygon", "bounds": [10, 10, 20, 20],
                               "points": [[10, 10], [30, 10], [31, 30]]})
        with self.assertRaises(SceneError):
            validate_scene(scene)
        scene = example_scene(); scene["items"][3]["bounds"] = [0, 0, 1, 1]
        with self.assertRaises(SceneError):
            validate_scene(scene)

    def test_edge_through_content_is_hard_failure(self) -> None:
        scene = example_scene()
        scene["items"].append({"id": "note", "type": "text", "bounds": [285, 115, 50, 40],
                               "font_size": 10, "text": "note"})
        qa = validate_scene(scene)
        self.assertFalse(qa["renderable"])
        self.assertTrue(any(i["code"] == "edge_crosses_content" for i in qa["issues"]))

    def test_arrowhead_triangle_overlap_is_not_missed_at_endpoint(self) -> None:
        scene = example_scene()
        scene["items"].append({"id": "near-tip", "type": "text", "bounds": [382, 121, 16, 18],
                               "font_size": 9, "text": "x"})
        qa = validate_scene(scene)
        self.assertTrue(any(i["code"] == "arrowhead_overlaps_content" and i["obstacle"] == "near-tip"
                            for i in qa["issues"]))

    def test_font_floor_canvas_and_real_text_overflow_are_errors(self) -> None:
        scene = example_scene()
        scene["items"].append({"id": "tiny", "type": "text", "bounds": [590, 300, 30, 30],
                               "font_size": 5, "text": "this text cannot fit"})
        codes = {i["code"] for i in validate_scene(scene)["issues"]}
        self.assertGreaterEqual(codes, {"outside_canvas", "font_below_minimum", "text_overflow"})

    def test_schema_rejects_remote_assets_and_unsafe_formula(self) -> None:
        scene = example_scene()
        scene["items"].append({"id": "remote", "type": "image", "bounds": [10, 10, 20, 20],
                               "source": "https://example.com/a.png"})
        with self.assertRaises(SceneError):
            validate_scene(scene)
        scene = example_scene(); scene["items"][4]["latex"] = r"\input{secret}"
        self.assertTrue(any(i["code"] == "formula_unsupported" for i in validate_scene(scene)["issues"]))

    def test_alpha_bbox_drives_image_occupancy_and_path_is_confined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); asset = root / "asset.png"
            image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((40, 40, 59, 59), fill="red"); image.save(asset)
            scene = example_scene()
            scene["items"].append({"id": "asset", "type": "image", "bounds": [250, 20, 100, 100],
                                   "source": "asset.png", "fit": "contain"})
            svg, qa = render_svg(scene, base_dir=root)
            self.assertTrue(qa["ok"])
            self.assertEqual(qa["item_bounds"]["asset"], [290.0, 60.0, 20.0, 20.0])
            self.assertIn("data:image/png;base64,", svg)
            scene["items"][-1]["source"] = "../outside.png"
            with self.assertRaises(SceneError):
                render_svg(scene, base_dir=root)

    def test_no_arbitrary_top_level_or_style_fields(self) -> None:
        scene = example_scene(); scene["execute"] = "anything"
        with self.assertRaises(SceneError): validate_scene(scene)
        scene = example_scene(); scene["items"][0]["style"]["onclick"] = "bad()"
        with self.assertRaises(SceneError): validate_scene(scene)

    def test_unavailable_requested_font_is_explicitly_substituted_without_tofu(self) -> None:
        scene = example_scene()
        scene["items"][2]["text"] = "video → tokens"
        scene["items"][2]["style"]["font_family"] = "DejaVu Sans"
        svg, qa = render_svg(scene)
        self.assertIn('font-family="Arial Unicode MS"', svg)
        self.assertTrue(any(i["code"] == "font_substituted" for i in qa["issues"]))
        self.assertFalse(any(i["code"] == "missing_glyphs" for i in qa["issues"]))

    def test_formula_has_final_size_floor(self) -> None:
        scene = example_scene()
        scene["items"][4]["bounds"] = [230, 235, 8, 4]
        self.assertTrue(any(i["code"] == "formula_below_minimum" for i in validate_scene(scene)["issues"]))

    def test_text_endpoint_cannot_bypass_collision_and_polyline_gap_is_exact(self) -> None:
        scene = example_scene()
        scene["items"][3].update({"source": "label-left", "points": [[45, 120], [399, 120]]})
        scene["items"][3].pop("curve")
        scene["items"].append({"id": "sliver", "type": "text", "bounds": [301, 116, 3, 8],
                               "font_size": 5.5, "text": "."})
        codes = {i["code"] for i in validate_scene(scene)["issues"]}
        self.assertIn("invalid_edge_endpoint", codes)
        self.assertIn("edge_crosses_content", codes)

    def test_crossing_claim_is_not_a_schema_escape(self) -> None:
        scene = example_scene()
        scene["items"][3]["crossing"] = "explained"
        with self.assertRaises(SceneError):
            validate_scene(scene)


if __name__ == "__main__":
    unittest.main()
