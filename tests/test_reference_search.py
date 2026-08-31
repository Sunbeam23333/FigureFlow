from __future__ import annotations

import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_core import reference_search  # noqa: E402
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
        self.assertEqual(query["iiprop"], ["url|mime|extmetadata"])
        self.assertEqual(query["gsrnamespace"], ["6"])

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
