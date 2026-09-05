from __future__ import annotations

import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from PIL import Image, PngImagePlugin


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_core import reference_search  # noqa: E402
from demo_core.reference_import import (  # noqa: E402
    DownloadPayload,
    ReferenceImportError,
    materialize_reference_assets,
)
from demo_core.schemas import ReferenceAsset  # noqa: E402


class ReferenceProviderTests(unittest.TestCase):
    def test_offline_and_user_url_providers_never_fetch(self) -> None:
        with patch.object(reference_search, "urlopen", side_effect=AssertionError("network must stay off")):
            offline = reference_search.search_references("", provider="offline-example", limit=1)
            user = reference_search.search_references(
                "",
                provider="user-url",
                user_urls=["https://example.org/reference.png?token=do-not-persist#crop"],
            )
        self.assertEqual(offline[0].uri, "example://figureflow/examples/figureflow_workflow.png")
        self.assertEqual(user[0].uri, "https://example.org/reference.png")
        self.assertIn("license and reuse rights require review", user[0].attribution or "")

    def test_user_url_rejects_credentials(self) -> None:
        with self.assertRaises(ValueError):
            reference_search.search_references(
                "",
                provider="user-url",
                user_urls=["https://user:secret@example.org/reference.png"],
            )

    def test_schema_strips_query_secrets_from_direct_reference_injection(self) -> None:
        asset = ReferenceAsset(
            id="direct-reference",
            title="Direct reference",
            uri="https://example.org/reference.png?X-Amz-Signature=secret#crop",
            source_url="https://example.org/source?id=42&token=secret#details",
            source_type="user-url",
            provider="unit-static",
        )
        self.assertEqual(asset.uri, "https://example.org/reference.png")
        self.assertEqual(asset.source_url, "https://example.org/source")

    def test_wikimedia_filters_non_raster_and_incomplete_license_metadata(self) -> None:
        captured: list[str] = []

        def transport(url: str, timeout: float):
            captured.append(url)
            self.assertEqual(timeout, 3.0)
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 11,
                            "title": "File:GPU cluster.jpg",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/gpu.jpg",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:GPU_cluster.jpg",
                                    "mime": "image/jpeg",
                                    "extmetadata": {
                                        "Artist": {"value": "<b>CSIRO</b>"},
                                        "LicenseShortName": {"value": "CC BY 3.0"},
                                        "LicenseUrl": {"value": "//creativecommons.org/licenses/by/3.0/"},
                                    },
                                }
                            ],
                        },
                        {
                            "pageid": 12,
                            "title": "File:Architecture.pdf",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/architecture.pdf",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Architecture.pdf",
                                    "mime": "application/pdf",
                                    "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}},
                                }
                            ],
                        },
                        {
                            "pageid": 13,
                            "title": "File:No license.png",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/no-license.png",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:No_license.png",
                                    "mime": "image/png",
                                    "extmetadata": {},
                                }
                            ],
                        },
                    ]
                }
            }

        provider = reference_search.WikimediaCommonsProvider(transport=transport, timeout=3.0)
        assets = provider.search(reference_search.ReferenceSearchRequest("GPU cluster", limit=3))
        self.assertEqual([asset.id for asset in assets], ["wm-11"])
        self.assertEqual(assets[0].author, "CSIRO")
        self.assertEqual(assets[0].license_url, "https://creativecommons.org/licenses/by/3.0/")
        query = parse_qs(urlsplit(captured[0]).query)
        self.assertEqual(urlsplit(captured[0]).netloc, "commons.wikimedia.org")
        self.assertEqual(query["iiprop"], ["url|mime|size|extmetadata"])
        self.assertEqual(query["iiurlwidth"], ["1600"])
        self.assertEqual(query["gsrnamespace"], ["6"])

    def test_wikimedia_filters_licenses_outside_the_import_allowlist(self) -> None:
        def transport(url: str, timeout: float):
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 14,
                            "title": "File:Noncommercial.png",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/wikipedia/commons/a/aa/Noncommercial.png",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Noncommercial.png",
                                    "mime": "image/png",
                                    "width": 800,
                                    "height": 600,
                                    "extmetadata": {
                                        "Artist": {"value": "Example creator"},
                                        "LicenseShortName": {"value": "CC BY-NC 4.0"},
                                        "LicenseUrl": {
                                            "value": "https://creativecommons.org/licenses/by-nc/4.0/"
                                        },
                                    },
                                }
                            ],
                        }
                    ]
                }
            }

        provider = reference_search.WikimediaCommonsProvider(transport=transport, timeout=3.0)
        assets = provider.search(reference_search.ReferenceSearchRequest("noncommercial", limit=1))
        self.assertEqual(assets, [])

    def test_commons_result_can_be_safely_imported_and_metadata_is_stripped(self) -> None:
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private-note", "must not survive")
        buffer = BytesIO()
        Image.new("RGB", (320, 180), "#4B79A1").save(buffer, format="PNG", pnginfo=metadata)
        image_bytes = buffer.getvalue()
        asset = ReferenceAsset(
            id="wm-101",
            title="Open GPU facility reference",
            uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/GPU_facility.png",
            original_uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/GPU_facility.png",
            source_url="https://commons.wikimedia.org/wiki/File:GPU_facility.png",
            source_type="provider-search",
            provider="wikimedia-commons",
            author="Example Author",
            license_name="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            attribution="Example Author / CC BY-SA 4.0",
            declared_mime_type="image/png",
            declared_width_px=320,
            declared_height_px=180,
        )

        def transport(url: str, timeout: float, max_bytes: int) -> DownloadPayload:
            self.assertEqual(url, asset.uri)
            self.assertGreater(timeout, 0)
            self.assertGreater(max_bytes, len(image_bytes))
            return DownloadPayload(
                data=image_bytes,
                content_type="image/png",
                final_url=url,
                content_length=len(image_bytes),
            )

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            imported = materialize_reference_assets(
                [asset], run_dir, selected_ids=[asset.id], transport=transport
            )
            self.assertEqual(len(imported), 1)
            source = Path(imported[0].source_path)
            self.assertTrue(source.is_file())
            with Image.open(source) as normalized:
                self.assertEqual(normalized.size, (320, 180))
                self.assertNotIn("private-note", normalized.info)
            manifest = Path(imported[0].manifest_path).read_text(encoding="utf-8")
            self.assertIn('"network_fetched": true', manifest)
            self.assertIn('"redirects_allowed": false', manifest)
            self.assertNotIn(str(run_dir), manifest)

    def test_user_url_cannot_cross_the_network_import_boundary(self) -> None:
        asset = reference_search.search_references(
            "", provider="user-url", user_urls=["https://example.org/reference.png"]
        )[0]
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ReferenceImportError):
            materialize_reference_assets(
                [asset],
                Path(temporary),
                selected_ids=[asset.id],
                transport=lambda *_: (_ for _ in ()).throw(AssertionError("must not fetch")),
            )

    def test_import_rejects_content_type_or_search_dimension_mismatch(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (320, 180), "#4B79A1").save(buffer, format="PNG")
        asset = ReferenceAsset(
            id="wm-102",
            title="Mismatched reference",
            uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/mismatch.png",
            source_url="https://commons.wikimedia.org/wiki/File:Mismatch.png",
            source_type="provider-search",
            provider="wikimedia-commons",
            author="Example Author",
            license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            declared_mime_type="image/png",
            declared_width_px=640,
            declared_height_px=180,
        )
        payload = DownloadPayload(
            data=buffer.getvalue(),
            content_type="image/png",
            final_url=asset.uri,
            content_length=len(buffer.getvalue()),
        )
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ReferenceImportError):
            materialize_reference_assets(
                [asset], Path(temporary), selected_ids=[asset.id], transport=lambda *_: payload
            )

    def test_import_rejects_source_page_that_names_another_commons_file(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (320, 180), "#4B79A1").save(buffer, format="PNG")
        asset = ReferenceAsset(
            id="wm-103",
            title="Mismatched source",
            uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/Expected.png",
            source_url="https://commons.wikimedia.org/wiki/File:Different.png",
            source_type="provider-search",
            provider="wikimedia-commons",
            author="Example Author",
            license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
        )
        payload = DownloadPayload(
            data=buffer.getvalue(),
            content_type="image/png",
            final_url=asset.uri,
            content_length=len(buffer.getvalue()),
        )
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ReferenceImportError):
            materialize_reference_assets(
                [asset], Path(temporary), selected_ids=[asset.id], transport=lambda *_: payload
            )

    def test_import_rejects_original_uri_that_names_another_commons_file(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (320, 180), "#4B79A1").save(buffer, format="PNG")
        asset = ReferenceAsset(
            id="wm-104",
            title="Spoofed original reference",
            uri="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Actual.png/320px-Actual.png",
            original_uri="https://upload.wikimedia.org/wikipedia/commons/a/ab/Expected.png",
            source_url="https://commons.wikimedia.org/wiki/File:Expected.png",
            source_type="provider-search",
            provider="wikimedia-commons",
            author="Example Author",
            license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
        )
        payload = DownloadPayload(
            data=buffer.getvalue(),
            content_type="image/png",
            final_url=asset.uri,
            content_length=len(buffer.getvalue()),
        )
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ReferenceImportError):
            materialize_reference_assets(
                [asset], Path(temporary), selected_ids=[asset.id], transport=lambda *_: payload
            )

    def test_custom_provider_registration_is_pluggable(self) -> None:
        class StaticProvider:
            name = "unit-static"

            def search(self, request: reference_search.ReferenceSearchRequest):
                return reference_search.OfflineExampleProvider().search(request)

        reference_search.register_reference_provider("unit-static", StaticProvider, replace=True)
        assets = reference_search.search_references("anything", provider="unit-static", limit=1)
        self.assertEqual(assets[0].provider, "offline-example")


if __name__ == "__main__":
    unittest.main()
