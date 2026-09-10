from __future__ import annotations

import base64
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from demo_core.scene import SceneError, render_scene, render_svg, validate_scene
from demo_core.svg_assets import (
    MAX_BYTES, SVGAssetError, inspect_svg, raster_preview, safe_svg_bytes,
)


def svg(content: str, attributes: str = 'viewBox="0 0 100 100"') -> bytes:
    return ('<svg xmlns="http://www.w3.org/2000/svg" ' + attributes + '>' + content + '</svg>').encode()


def gradient(color: str) -> bytes:
    return svg('<defs><linearGradient id="paint"><stop offset="0" stop-color="' + color +
               '"/><stop offset="1" stop-color="' + color + '"/></linearGradient>'
               '<clipPath id="clip"><rect width="100" height="100"/></clipPath></defs>'
               '<g clip-path="url(#clip)"><rect width="100" height="100" fill="url(#paint)"/></g>')


def image_scene(*names: str) -> dict:
    return {"canvas": {"width": 100 * len(names), "height": 100},
            "items": [{"id": "asset" + str(index), "type": "image", "source": name,
                       "bounds": [100 * index, 0, 100, 100]} for index, name in enumerate(names)]}


class SVGAssetTests(unittest.TestCase):
    def test_static_lucide_style_and_current_color_are_preserved(self) -> None:
        data = svg('<path d="M10 10 H90 V90 H10 Z"/>',
                   'width="24" height="24" viewBox="0 0 100 100" fill="none" '
                   'stroke="currentColor" stroke-width="2" stroke-linecap="round"')
        safe = safe_svg_bytes(data, color="#16827a")
        self.assertIn(b'stroke="#16827a"', safe)
        self.assertNotIn(b'currentColor', safe)
        self.assertEqual(inspect_svg(data)["aspect_ratio"], 1)
        self.assertTrue(raster_preview(data).startswith(b"\x89PNG"))

    def test_simple_styles_are_flattened_and_local_gradients_and_clip_paths_survive(self) -> None:
        data = svg('<defs><style>.paint{fill:url(#paint)}.clear{fill:none}</style>'
                   '<radialGradient id="paint" cx=".5" cy=".5" r=".5">'
                   '<stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/>'
                   '</radialGradient><clipPath id="clip"><circle cx="50" cy="50" r="40"/>'
                   '</clipPath></defs><g style="clip-path:url(#clip)">'
                   '<rect class="paint" width="100" height="100"/></g>')
        safe = safe_svg_bytes(data, prefix="one")
        self.assertNotIn(b"<style", safe)
        self.assertNotIn(b"class=", safe)
        self.assertIn(b'id="one-paint"', safe)
        self.assertIn(b'fill="url(#one-paint)"', safe)
        self.assertIn(b'clip-path="url(#one-clip)"', safe)
        with Image.open(io.BytesIO(raster_preview(data))) as image:
            self.assertEqual(image.convert("RGBA").getpixel((0, 0))[3], 0)
            self.assertGreater(image.convert("RGBA").getpixel((256, 256))[0], 240)

    def test_editor_metadata_is_stripped_and_unicode_ids_are_safely_namespaced(self) -> None:
        data = svg('<defs><linearGradient id="渐变"><stop offset="0" stop-color="red"/>'
                   '</linearGradient></defs><g id="图层_2" data-name="图层 2" aria-label="icon" role="img">'
                   '<rect width="100" height="100" fill="url(#渐变)"/></g>')
        safe = safe_svg_bytes(data, prefix="official").decode()
        self.assertIn('id="official-图层_2"', safe)
        self.assertIn('fill="url(#official-渐变)"', safe)
        for attribute in ('data-name=', 'aria-label=', 'role='):
            self.assertNotIn(attribute, safe)
        self.assertTrue(raster_preview(data))

    def test_original_intrinsic_ratio_and_view_box_are_not_rewritten(self) -> None:
        data = svg('<rect width="100" height="100" fill="red"/>',
                   'width="200px" height="100px" viewBox="0 0 100 100"')
        info = inspect_svg(data)
        self.assertEqual(info["aspect_ratio"], 2)
        self.assertEqual(info["view_box"], [0, 0, 100, 100])
        with Image.open(io.BytesIO(raster_preview(data, max_side=200))) as image:
            self.assertEqual(image.size, (200, 100))
            self.assertEqual(image.convert("RGBA").getchannel("A").getbbox(), (50, 0, 150, 100))

    def test_official_absolute_units_and_hidden_viewport_crop_are_preserved(self) -> None:
        data = svg('<rect width="200" height="100" fill="red"/>',
                   'width="100pt" height="50pt" viewBox="50 0 100 50" overflow="hidden"')
        info = inspect_svg(data)
        self.assertAlmostEqual(info["width"], 100 * 96 / 72)
        self.assertEqual(info["aspect_ratio"], 2)
        self.assertEqual(info["view_box"], [50, 0, 100, 50])
        self.assertIn(b'overflow="hidden"', safe_svg_bytes(data))
        self.assertTrue(raster_preview(data))
        with self.assertRaises(SVGAssetError):
            safe_svg_bytes(svg('', 'viewBox="0 0 100 100" overflow="visible"'))
        with self.assertRaises(SVGAssetError):
            safe_svg_bytes(svg('', 'width="1em" height="1em"'))

    def test_verified_embedded_raster_with_clip_and_gradient_is_allowed(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "#2155aa").save(buffer, format="JPEG")
        uri = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
        data = svg('<defs><clipPath id="clip"><circle cx="50" cy="50" r="40"/></clipPath>'
                   '</defs><g clip-path="url(#clip)"><image href="' + uri +
                   '" width="100" height="100"/></g>')
        self.assertEqual(inspect_svg(data)["embedded_raster_count"], 1)
        self.assertTrue(raster_preview(data).startswith(b"\x89PNG"))

    def test_nested_svg_data_uri_fake_mime_and_corrupt_raster_are_rejected(self) -> None:
        nested = base64.b64encode(svg('<script/>')).decode()
        for uri in ("data:image/svg+xml;base64," + nested, "data:image/png;base64," + nested,
                    "data:image/png;base64,eA==", "data:image/jpeg;base64,***"):
            with self.subTest(uri=uri[:25]), self.assertRaises(SVGAssetError):
                safe_svg_bytes(svg('<image width="10" height="10" href="' + uri + '"/>'))

    def test_small_compressed_raster_cannot_bypass_decoded_dimension_budget(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (4097, 1), "white").save(buffer, format="PNG")
        self.assertLess(len(buffer.getvalue()), 4096)
        uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        with self.assertRaises(SVGAssetError):
            safe_svg_bytes(svg('<image width="100" height="100" href="' + uri + '"/>'))

    def test_xml_entities_processing_instructions_and_foreign_namespaces_are_rejected(self) -> None:
        for data in (
            b'<!DOCTYPE svg [<!ENTITY x "bad">]><svg><title>&x;</title></svg>',
            b'<!DOCTYPE svg SYSTEM "https://example.com/x"><svg/>',
            b'<?xml-stylesheet href="file:///secret"?><svg/>',
            svg('<xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="file:///secret"/>'),
            '<svg viewBox="0 0 10 10"/>'.encode("utf-16"),
        ):
            with self.subTest(data=data[:55]), self.assertRaises(SVGAssetError):
                safe_svg_bytes(data)

    def test_unsupported_elements_events_and_external_references_fail_closed(self) -> None:
        bodies = ['<' + name + '/>' for name in
                  ("script", "SCRIPT", "foreignObject", "animate", "set", "use", "svg", "mask", "filter")]
        bodies += ['<g ' + attribute + '="alert(1)"/>' for attribute in ("onclick", "ONLOAD", "onLoad")]
        bodies += ['<g xml:base="https://example.com/"/>']
        for target in ("https://example.com/a.png", "//example.com/a.png", "file:///secret", "../secret",
                       "javascript:alert(1)"):
            bodies.append('<image width="10" height="10" href="' + target + '"/>')
            bodies.append('<path fill="url(' + target + ')"/>')
        bodies.append('<g xmlns:bad="urn:foreign" bad:onload="alert(1)"/>')
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(SVGAssetError):
                safe_svg_bytes(svg(body))

    def test_css_external_and_dynamic_syntax_cannot_bypass_attribute_checks(self) -> None:
        for declaration in (
            'fill:url(https://example.com/a)', 'fill:url(#ok) url(https://example.com/a)',
            r'fill:u\72l(https://example.com/a)', 'fill:var(--color)',
            'fill:expression(alert(1))', 'fill:image-set(url(https://example.com/a))',
            'clip-path:url(file:///secret)', 'fill:red!important', 'fill:/*x*/red',
        ):
            for body in ('<path style="' + declaration + '"/>',
                         '<style>.x{' + declaration + '}</style><path class="x"/>'):
                with self.subTest(body=body), self.assertRaises(SVGAssetError):
                    safe_svg_bytes(svg(body))
        for stylesheet in ('@import "https://example.com/x";', '#x{fill:red}',
                           '@font-face{src:url(https://example.com/x)}', '.a .b{fill:red}', '.a.b{fill:red}'):
            with self.assertRaises(SVGAssetError):
                safe_svg_bytes(svg('<style>' + stylesheet + '</style>'))

    def test_duplicate_missing_wrong_type_and_cyclic_references_are_rejected(self) -> None:
        for body in (
            '<path id="same"/><path id="same"/>',
            '<path fill="url(#missing)"/>',
            '<defs><clipPath id="clip"/></defs><path fill="url(#clip)"/>',
            '<defs><linearGradient id="a" href="#a"/></defs>',
            '<defs><linearGradient id="a" href="#b"/><linearGradient id="b" href="#a"/></defs>',
            '<defs><clipPath id="a" clip-path="url(#a)"><path/></clipPath></defs>',
            '<defs><clipPath id="a"><g clip-path="url(#a)"><path/></g></clipPath></defs>',
        ):
            with self.subTest(body=body), self.assertRaises(SVGAssetError):
                safe_svg_bytes(svg(body))
        valid = svg('<defs><linearGradient id="a"><stop offset="0" stop-color="red"/>'
                    '</linearGradient><linearGradient id="b" href="#a"/></defs>'
                    '<rect width="100" height="100" fill="url(#b)"/>')
        self.assertTrue(raster_preview(valid))

    def test_resource_and_nonfinite_coordinate_limits(self) -> None:
        for data in (
            b" " * (MAX_BYTES + 1),
            svg("<g>" * 34 + "</g>" * 34),
            svg("<path/>" * 2001),
            svg('<path d="' + "M0 0 " * 27000 + '"/>'),
            svg('<rect width="1e309" height="1"/>'),
            svg('<g transform="matrix(NaN 0 0 1 0 0)"/>'),
            svg('<path stroke-width="1000001"/>'),
            svg('<path d="M"/>'),
            svg('<path d="M0 0 L10"/>'),
            svg('<path d="M0 0 A10 10 0 2 0 5 5"/>'),
            svg('', 'viewBox="0 0 0 10"'),
            svg('', 'viewBox="0 0 999999 10"'),
            svg('', 'viewBox="0 0 -1 10"'),
            svg('', 'viewBox="0 0 1e-320 1e-320"'),
        ):
            with self.subTest(data=data[:60]), self.assertRaises(SVGAssetError):
                safe_svg_bytes(data)
        for size in (True, -1, 0, 2049, 512.5):
            with self.assertRaises(SVGAssetError):
                raster_preview(gradient("red"), max_side=size)

    def test_repeated_reference_graph_edges_have_linear_bounded_traversal(self) -> None:
        definitions = []
        for index in range(15):
            extra = (f' href="#g{index+1}" fill="url(#g{index+1})" stroke="url(#g{index+1})"'
                     if index < 14 else '')
            definitions.append(f'<linearGradient id="g{index}"{extra}/>')
        self.assertTrue(safe_svg_bytes(svg('<defs>' + ''.join(definitions) + '</defs>')))

    def test_renderer_has_no_network_or_file_fetch_capability(self) -> None:
        from demo_core.svg_assets import _local_raster_fetcher
        from demo_core.scene import _scene_asset_fetcher
        for target in ("http://127.0.0.1/", "file:///secret", "/tmp/image.png"):
            with self.assertRaises(SVGAssetError):
                _local_raster_fetcher(target, "image/*")
            with self.assertRaises(SceneError):
                _scene_asset_fetcher(target, "image/*")
        with patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
            self.assertTrue(raster_preview(gradient("#ee3355"), max_side=64))


class SceneSVGAssetTests(unittest.TestCase):
    def test_two_assets_with_same_defs_preserve_colors_and_export_without_source_files(self) -> None:
        import cairosvg
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "red.svg").write_bytes(gradient("red"))
            (root / "blue.svg").write_bytes(gradient("blue"))
            result = render_scene(image_scene("red.svg", "blue.svg"), root / "figure",
                                  formats=("svg", "png", "pdf"), base_dir=root)
            self.assertTrue(result["qa"]["renderable"])
            content = Path(result["paths"]["svg"]).read_bytes()
            parsed = ET.fromstring(content)
            identifiers = [node.get("id") for node in parsed.iter() if node.get("id")]
            self.assertEqual(len(identifiers), len(set(identifiers)))
            self.assertNotIn(b"data:image/svg", content)
            self.assertGreaterEqual(len(parsed.findall('.//{http://www.w3.org/2000/svg}linearGradient')), 2)
            self.assertTrue(Path(result["paths"]["pdf"]).read_bytes().startswith(b"%PDF"))
            (root / "red.svg").unlink(); (root / "blue.svg").unlink()
            portable = cairosvg.svg2png(bytestring=content, output_width=200, output_height=100)
            with Image.open(io.BytesIO(portable)) as image:
                self.assertEqual(image.convert("RGB").getpixel((50, 50)), (255, 0, 0))
                self.assertEqual(image.convert("RGB").getpixel((150, 50)), (0, 0, 255))

    def test_image_alpha_qa_preserves_original_ratio_and_asset_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "wide.svg").write_bytes(svg('<rect x="50" y="25" width="100" height="50" fill="red"/>',
                                                  'viewBox="0 0 200 100"'))
            scene = {"canvas": {"width": 240, "height": 240}, "items": [
                {"id": "logo", "type": "image", "source": "wide.svg", "bounds": [20, 20, 200, 200]},
            ]}
            qa = validate_scene(scene, base_dir=root)
            for actual, expected in zip(qa["item_bounds"]["logo"], [70, 95, 100, 50]):
                self.assertAlmostEqual(actual, expected, delta=0.5)
            scene["items"][0]["asset_bounds"] = [20, 30, 160, 80]
            qa = validate_scene(scene, base_dir=root)
            for actual, expected in zip(qa["item_bounds"]["logo"], [80, 70, 80, 40]):
                self.assertAlmostEqual(actual, expected, delta=0.5)

    def test_svg_prefix_is_reserved_against_scene_owned_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "a.svg").write_bytes(gradient("red"))
            scene = image_scene("a.svg")
            scene["items"].append({"id": "ffasset0-paint", "type": "shape", "bounds": [0, 0, 1, 1]})
            content, _ = render_svg(scene, base_dir=root)
            identifiers = [node.get("id") for node in ET.fromstring(content).iter() if node.get("id")]
            self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_asset_prefix_does_not_overlap_formula_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.svg").write_bytes(svg('<path id="figure_1" d="M0 0 H100 V100 H0 Z"/>'))
            scene = image_scene("a.svg")
            scene["items"].append({"id": "ffasset0", "type": "formula", "bounds": [0, 0, 20, 20],
                                   "latex": "x"})
            content, _ = render_svg(scene, base_dir=root)
            identifiers = [node.get("id") for node in ET.fromstring(content).iter() if node.get("id")]
            self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_scene_canvas_and_item_count_have_resource_limits(self) -> None:
        for dimensions in ((1e9, 1e9), (1e-320, 1), (5000, 5000)):
            scene = image_scene("a.svg")
            scene["canvas"].update(zip(("width", "height"), dimensions))
            with self.assertRaises(SceneError): validate_scene(scene)
        scene = image_scene("a.svg")
        scene["items"] = scene["items"] * 2001
        with self.assertRaises(SceneError): validate_scene(scene)

    def test_scene_rejects_svg_without_asset_root_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); assets = root / "assets"; assets.mkdir()
            (root / "outside.svg").write_bytes(gradient("red"))
            (assets / "escape.svg").symlink_to(root / "outside.svg")
            with self.assertRaises(SceneError): render_svg(image_scene("escape.svg"), base_dir=assets)
            with self.assertRaises(SceneError): render_svg(image_scene("outside.svg"))
            (assets / "bad.svg").write_bytes(svg('<script/>'))
            with self.assertRaises(SceneError): validate_scene(image_scene("bad.svg"), base_dir=assets)


if __name__ == "__main__":
    unittest.main()
