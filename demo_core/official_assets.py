"""Vetted official-brand catalog: source-linked lookup and bounded import.

This is a curated catalog, not web-wide search. Model-supplied URLs are never
downloaded. Brand marks retain their own rights; the project's MIT license
does not apply to them. Original bytes and deterministic derivatives coexist.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from PIL import Image

from .reference_import import _fixed_host_download


class OfficialAssetError(ValueError):
    """A catalog item failed closed; no replacement artwork was invented."""


@dataclass(frozen=True)
class OfficialAsset:
    id: str
    title: str
    keywords: str
    source_page: str
    asset_url: str
    sha256: str
    format: str
    crop: tuple[int, int, int, int] | None = None
    viewbox: str | None = None
    note: str = "Brand identifier, not an endorsement or a model-version badge."

    def record(self):
        return {**asdict(self), "provider": "official-brand", "rights": "Brand/trademark rights remain with the owner; check applicable brand-use guidance."}


# Reviewed primary-source links. Updates require human source/visual review,
# not a model's guessed host, URL, or logo. Checksums detect changed resources.
CATALOG = (
    OfficialAsset("official-qwen-omni", "Qwen2.5-Omni", "qwen qwen2.5-omni 通义 千问",
        "https://github.com/QwenLM/Qwen2.5-Omni",
        "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen2.5-Omni/Omni_logo.png",
        "d4cf58febcdebe857cc24c3f1fd211437acc2a7cf02e65e7427a822446bedfbf", "png"),
    OfficialAsset("official-hunyuan", "Tencent Hunyuan", "hunyuan 混元 tencent 腾讯",
        "https://github.com/Tencent-Hunyuan/Tencent-Hunyuan-Large",
        "https://dscache.tencent-cloud.cn/upload/uploader/hunyuan-64b418fd052c033b228e04bc77bbc4b54fd7f5bc.png",
        "25a708b5c10c3e5ecac76607d98feeb6111fa2b9159d4e5eb3346b25428678dd", "png"),
    OfficialAsset("official-gemini", "Google Gemini", "gemini google 谷歌",
        "https://gemini.google.com/",
        "https://www.gstatic.com/lamda/images/gemini_sparkle_aurora_33f86dc0c0257da337c63.svg",
        "f56df33f86dc0c0257da337c63bf7ad68c0a1b27b796ec707e147984351bccb3", "svg",
        note="Current Gemini family mark; pair with editable exact model text, not a claimed version-specific logo."),
    OfficialAsset("official-bilibili", "bilibili", "bilibili b站 哔哩哔哩",
        "https://ir.bilibili.com/", "https://ir.bilibili.com/media/mwvbaepv/logoenblue.svg",
        "359a7647e98b2628846547423177d265ae2b61f5829526996086cddd72fc2dfe", "svg", viewbox="0 0 93 40",
        note="Viewport crop removes the separate Investor Home descriptor; original paths and colors stay unchanged."),
    OfficialAsset("official-youtube", "YouTube", "youtube 视频",
        "https://developers.google.com/youtube/terms/branding-guidelines",
        "https://developers.google.com/static/youtube/images/youtube-logos-2x.png",
        "aa92c3f8a5d0dd21213371139ab8a245911704000bcffb8a15d6db2b43f5151c", "png", crop=(55, 69, 355, 137)),
    OfficialAsset("official-douyin", "抖音", "douyin 抖音",
        "https://creator.douyin.com/",
        "https://lf-fe-creator.douyinstatic.com/obj/douyn-creator-scm-cdn/douyin-creator-master-new/static/image/douyin-creator-logo-v2.4df2b1a4.png",
        "8173335d2a6b73746e630e3f355dbc9f96b89dc273b864691626a4eb21cc0fd8", "png", crop=(0, 0, 520, 201),
        note="Official Chinese Douyin mark; viewport crop excludes Creator Center, not an international TikTok wordmark."),
)


def search_official(query: str, limit: int = 3) -> list[dict]:
    if not isinstance(query, str) or not query.strip() or len(query) > 300 or type(limit) is not int or not 1 <= limit <= 3:
        raise OfficialAssetError("query and limit 1..3 are required")
    tokens = query.casefold().split()
    ranked = [(sum(t in (a.title + " " + a.keywords).casefold() for t in tokens), a) for a in CATALOG]
    return [a.record() for score, a in sorted(ranked, key=lambda x: -x[0]) if score][:limit]


def import_official(asset_id: str, output_dir: str | Path, *, transport=None) -> dict:
    """Fetch one immutable catalog ID, retain its original, and render safely.

    The callable transport is only for host-side testing, never a model tool.
    No redirects, arbitrary hosts, fallback artwork, matte removal or recolor.
    """
    asset = next((a for a in CATALOG if a.id == asset_id), None)
    if asset is None:
        raise OfficialAssetError("unknown official catalog id")
    url = urlsplit(asset.asset_url)
    if url.scheme != "https" or url.username or url.password or url.port not in (None, 443) or url.fragment:
        raise OfficialAssetError("invalid catalog URL")
    root = Path(output_dir).resolve() / asset.id
    if root.exists():
        raise OfficialAssetError("asset already imported; choose a fresh output directory")
    payload = (transport or _fixed_host_download)(asset.asset_url, 20.0, 12 * 1024 * 1024)
    raw = payload.data
    if payload.final_url != asset.asset_url or not raw or len(raw) > 12 * 1024 * 1024:
        raise OfficialAssetError("unexpected response URL or byte size")
    if payload.content_length is not None and payload.content_length != len(raw):
        raise OfficialAssetError("response length mismatch")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != asset.sha256:
        raise OfficialAssetError("official resource changed; review its source and artwork before updating the catalog")
    if asset.format == "svg":
        from .svg_assets import safe_svg_bytes, raster_preview
        if payload.content_type.split(";", 1)[0] not in {"image/svg+xml", "application/xml", "text/xml"}:
            raise OfficialAssetError("unexpected SVG media type")
        rendered = safe_svg_bytes(raw, prefix=asset.id)
        if asset.viewbox:
            tree = ET.fromstring(rendered)
            tree.set("viewBox", asset.viewbox)
            _, _, width, height = asset.viewbox.split()
            tree.set("width", width)
            tree.set("height", height)
            tree.set("overflow", "hidden")
            rendered = ET.tostring(tree, encoding="utf-8")
        preview = raster_preview(rendered)
    else:
        if payload.content_type.split(";", 1)[0] != "image/png":
            raise OfficialAssetError("unexpected raster media type")
        with Image.open(io.BytesIO(raw)) as im:
            if im.format != "PNG" or max(im.size) > 8192 or im.width * im.height > 40_000_000:
                raise OfficialAssetError("unsafe raster dimensions or format")
            im.load()
            if asset.crop:
                x0, y0, x1, y1 = asset.crop
                if not (0 <= x0 < x1 <= im.width and 0 <= y0 < y1 <= im.height):
                    raise OfficialAssetError("catalog crop falls outside the image")
                im = im.crop(asset.crop)
            buffer = io.BytesIO()
            im.save(buffer, format="PNG")
            rendered = buffer.getvalue()
        preview = rendered
    provenance = {**asset.record(), "original_sha256": digest,
        "render_sha256": hashlib.sha256(rendered).hexdigest(),
        "processing": "Original artwork; safe format conversion and catalog viewport crop only. No AI redraw, recolor or background removal."}
    # Validation happens before writes; reserve a new directory, never overwrite.
    root.mkdir(parents=True, exist_ok=False)
    original_path = root / f"original.{asset.format}"
    render_path = root / f"render.{asset.format}"
    preview_path = root / "preview.png"
    original_path.write_bytes(raw)
    render_path.write_bytes(rendered)
    preview_path.write_bytes(preview)
    (root / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": asset.id, "path": str(render_path), "raw_path": str(original_path),
        "preview_path": str(preview_path), "kind": "official-brand", "meaning": asset.title,
        "provenance": provenance}
