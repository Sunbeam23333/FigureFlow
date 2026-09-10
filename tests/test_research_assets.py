from __future__ import annotations

import base64
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from PIL import Image

from demo_core.research_assets import ResearchAssetError, ResearchAssets
from demo_core.schemas import ReferenceAsset


def png_bytes(size=(320, 180)) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", size, "#FF00FF")
    for x in range(size[0] // 3, 2 * size[0] // 3):
        for y in range(size[1] // 3, 2 * size[1] // 3):
            image.putpixel((x, y), (30, 90, 180))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeGateway:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.pinned_reported_model = "gpt-5.6-sol-2026-07-09"

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class ResearchAssetsTests(unittest.TestCase):
    def test_capabilities_are_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            tools = ResearchAssets(FakeGateway(None), temporary)
            with self.assertRaises(ResearchAssetError):
                tools.search("robot")
            with self.assertRaises(ResearchAssetError):
                tools.generate_icon("robot", "robot gripper", [])

    def test_search_uses_only_commons_and_registry_ids(self):
        calls = []
        asset = ReferenceAsset(
            id="commons-one",
            title="Robot",
            uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/GPU_facility.png",
            source_type="provider-search",
            provider="wikimedia-commons",
            source_url="https://commons.wikimedia.org/wiki/File:GPU_facility.png",
            author="Author",
            license_name="Public domain",
        )

        def fake_search(query, **kwargs):
            calls.append((query, kwargs))
            return [asset]

        with tempfile.TemporaryDirectory() as temporary:
            tools = ResearchAssets(
                FakeGateway(None),
                temporary,
                allow_reference_search=True,
                search_fn=fake_search,
            )
            self.assertEqual(tools.search("robot", 1)[0]["id"], "commons-one")
            self.assertEqual(calls[0][1], {"provider": "wikimedia-commons", "limit": 1})
            with self.assertRaises(ResearchAssetError):
                tools.import_reference("invented-url")

    def test_import_reference_reuses_validated_import_and_preserves_credit(self):
        asset = ReferenceAsset(
            id="commons-one",
            title="Robot",
            uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/GPU_facility.png",
            original_uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/GPU_facility.png",
            source_type="provider-search",
            provider="wikimedia-commons",
            source_url="https://commons.wikimedia.org/wiki/File:GPU_facility.png",
            author="Author",
            license_name="Public domain",
            declared_mime_type="image/png",
            declared_width_px=320,
            declared_height_px=180,
        )

        def fake_search(*args, **kwargs):
            return [asset]

        def fake_transport(url, timeout, maximum):
            from demo_core.reference_import import DownloadPayload

            return DownloadPayload(png_bytes(), "image/png", url)

        with tempfile.TemporaryDirectory() as temporary:
            tools = ResearchAssets(
                FakeGateway(None),
                temporary,
                allow_reference_search=True,
                search_fn=fake_search,
                reference_transport=fake_transport,
            )
            tools.search("robot")
            result = tools.import_reference("commons-one")
            self.assertTrue(Path(result["path"]).is_file())
            self.assertEqual(result["provenance"]["author"], "Author")
            self.assertEqual(result["provenance"]["license_name"], "Public domain")
            self.assertNotIn("source_path", result["provenance"])
            self.assertNotIn(str(Path(temporary)), str(result["provenance"]))

    def test_process_existing_is_non_destructive_and_run_registered_only(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            run = Path(temporary)
            raw = run / "assets" / "user.png"
            raw.parent.mkdir()
            raw.write_bytes(png_bytes())
            original = raw.read_bytes()
            tools = ResearchAssets(FakeGateway(None), run)
            result = tools.process_existing(raw, id="local")
            self.assertEqual(raw.read_bytes(), original)
            self.assertNotEqual(Path(result["path"]), raw)
            external = Path(outside) / "external.png"
            external.write_bytes(png_bytes())
            with self.assertRaises(ResearchAssetError):
                tools.process_existing(external)

    def test_generate_icon_uses_sol_gateway_full_context_and_two_image_cap(self):
        encoded = base64.b64encode(png_bytes()).decode("ascii")
        response = SimpleNamespace(
            id="resp_image",
            output=[SimpleNamespace(type="image_generation_call", result=encoded)],
        )
        gateway = FakeGateway(response)
        context = [{"type": "input_text", "text": "FULL PAPER"}]
        with tempfile.TemporaryDirectory() as temporary:
            tools = ResearchAssets(gateway, temporary, allow_image_generation=True)
            first = tools.generate_icon("icon_one", "robot gripper", context)
            with self.assertRaises(ResearchAssetError):
                tools.generate_icon("icon_one", "duplicate", context)
            self.assertEqual(len(gateway.calls), 1)
            tools.generate_icon("icon_two", "camera", context)
            self.assertTrue(Path(first["raw_path"]).is_file())
            self.assertEqual(gateway.calls[0]["stage"], "asset_generation")
            sent_content = gateway.calls[0]["input"][0]["content"]
            self.assertEqual(sent_content[:-1], context)
            image_tool = gateway.calls[0]["tools"][0]
            self.assertEqual(image_tool["model"], "gpt-image-2")
            self.assertEqual(image_tool["quality"], "medium")
            with self.assertRaises(ResearchAssetError):
                tools.generate_icon("icon_three", "server", context)

    def test_generate_failure_has_no_fallback_or_partial_raw_file(self):
        response = {"id": "bad", "output": [{"type": "image_generation_call", "result": "bad"}]}
        gateway = FakeGateway(response)
        with tempfile.TemporaryDirectory() as temporary:
            tools = ResearchAssets(gateway, temporary, allow_image_generation=True)
            with self.assertRaises(ResearchAssetError):
                tools.generate_icon("bad_icon", "server", [])
            self.assertEqual(len(gateway.calls), 1)
            self.assertFalse((Path(temporary) / "research_assets" / "raw" / "bad_icon.png").exists())
            with self.assertRaises(ResearchAssetError):
                tools.generate_icon("bad_icon_two", "server", [])
            with self.assertRaises(ResearchAssetError):
                tools.generate_icon("bad_icon_three", "server", [])
            self.assertEqual(len(gateway.calls), 2)


if __name__ == "__main__":
    unittest.main()
