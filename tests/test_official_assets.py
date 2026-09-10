from dataclasses import replace
import hashlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pytest

from demo_core.official_assets import CATALOG, OfficialAssetError, search_official, import_official
from demo_core.reference_import import DownloadPayload
from demo_core.research_assets import ResearchAssets, ResearchAssetError


def fixture_asset():
    out = io.BytesIO()
    Image.new("RGBA", (40, 20), (10, 100, 200, 120)).save(out, format="PNG")
    data = out.getvalue()
    item = replace(CATALOG[-1], sha256=hashlib.sha256(data).hexdigest(), crop=(0, 0, 20, 20))
    return data, item


def test_catalog_is_source_linked_and_separates_douyin():
    result = search_official("抖音")
    assert len(result) == 1 and result[0]["id"] == "official-douyin"
    assert result[0]["source_page"].startswith("https://creator.douyin.com/")
    assert search_official("not-a-known-brand") == []
    for entry in CATALOG:
        assert len(entry.sha256) == 64 and entry.source_page.startswith("https://")


def test_import_preserves_original_and_color_alpha_and_provenance(tmp_path):
    data, item = fixture_asset()
    calls = []
    def transport(url, timeout, size):
        calls.append(url)
        return DownloadPayload(data, "image/png", url, len(data))
    with patch("demo_core.official_assets.CATALOG", (item,)):
        result = import_official(item.id, tmp_path, transport=transport)
    assert calls == [item.asset_url]
    assert Path(result["raw_path"]).read_bytes() == data
    with Image.open(result["path"]) as im:
        assert im.size == (20, 20) and im.getpixel((0, 0)) == (10, 100, 200, 120)
    assert result["provenance"]["source_page"] == item.source_page
    assert "MIT" not in result["provenance"]["rights"]


@pytest.mark.parametrize("failure", ["redirect", "checksum", "length", "type"])
def test_download_fails_closed_without_partial_asset(tmp_path, failure):
    data, item = fixture_asset()
    def transport(url, timeout, size):
        return DownloadPayload(data + (b"x" if failure == "checksum" else b""),
            "text/html" if failure == "type" else "image/png",
            "https://example.org/other" if failure == "redirect" else url,
            1 if failure == "length" else None)
    with patch("demo_core.official_assets.CATALOG", (item,)), pytest.raises(OfficialAssetError):
        import_official(item.id, tmp_path, transport=transport)
    assert not list(tmp_path.iterdir())


def test_arbitrary_url_never_reaches_transport(tmp_path):
    def forbidden(*args):
        raise AssertionError("network must not run")
    with pytest.raises(OfficialAssetError):
        import_official("https://example.org/logo.svg", tmp_path, transport=forbidden)


def test_research_tool_requires_grant_and_registered_id(tmp_path):
    a = ResearchAssets(None, tmp_path)
    with pytest.raises(ResearchAssetError):
        a.search("douyin", provider="official-brand")
    a.allow_reference_search = True
    with pytest.raises(ResearchAssetError):
        a.import_reference("official-douyin")
    assert a.search("douyin", provider="official-brand")[0]["id"] in a.registry
    with pytest.raises(ResearchAssetError):
        a.search("douyin", provider="arbitrary-url")
