"""Safely materialize allowlisted visual references into a FigureFlow run.

Search metadata is never treated as a fetch instruction by the renderer.  This
module is the only network-to-file bridge: it supports repository examples and
Wikimedia Commons records, refuses redirects and arbitrary hosts, validates the
declared license and decoded image, strips embedded metadata, and writes a
portable provenance record beside the normalized image.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image, ImageOps, UnidentifiedImageError

from .schemas import ReferenceAsset, supports_reference_import_license


ROOT = Path(__file__).resolve().parents[1]
MAX_IMPORTS = 3
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_DIMENSION = 8_192
MIN_IMAGE_DIMENSION = 64
DOWNLOAD_TIMEOUT_SECONDS = 20.0
COMMONS_MEDIA_HOSTS = frozenset({"upload.wikimedia.org", "thumb.wikimedia.org"})
COMMONS_SOURCE_HOST = "commons.wikimedia.org"
ALLOWED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
class ReferenceImportError(RuntimeError):
    """A safe, user-actionable import failure with no provider response body."""


@dataclass(frozen=True)
class DownloadPayload:
    """Bounded response data returned by the fixed-host transport."""

    data: bytes
    content_type: str
    final_url: str
    content_length: int | None = None


@dataclass(frozen=True)
class ReferenceImportResult:
    """Portable result describing one normalized local reference image."""

    id: str
    title: str
    provider: str
    source_path: str
    manifest_path: str
    source_url: str | None
    source_uri: str
    original_uri: str | None
    author: str | None
    license_name: str | None
    license_url: str | None
    attribution: str | None
    media_type: str
    width_px: int
    height_px: int
    bytes_received: int
    response_sha256: str
    normalized_sha256: str
    embedded_metadata_removed: bool


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _fixed_host_download(url: str, timeout: float, max_bytes: int) -> DownloadPayload:
    """Fetch one image without redirects from the validated Commons media host."""
    request = Request(
        url,
        headers={
            "User-Agent": "FigureFlow/0.2 (https://github.com/Sunbeam23333/FigureFlow; safe reference import)",
            "Accept": "image/jpeg,image/png,image/webp",
        },
    )
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:  # nosec B310 - host is checked before this call
            if response.getcode() != 200:
                raise ReferenceImportError("reference image server did not return HTTP 200")
            final_url = response.geturl()
            if final_url != url:
                raise ReferenceImportError("reference image redirects are not allowed")
            content_type = str(response.headers.get_content_type()).lower()
            raw_length = response.headers.get("Content-Length")
            content_length = int(raw_length) if raw_length and raw_length.isdigit() else None
            if content_length is not None and content_length > max_bytes:
                raise ReferenceImportError("reference image exceeds the 12 MB download limit")
            chunks: list[bytes] = []
            received = 0
            while True:
                chunk = response.read(min(1024 * 1024, max_bytes + 1 - received))
                if not chunk:
                    break
                received += len(chunk)
                if received > max_bytes:
                    raise ReferenceImportError("reference image exceeds the 12 MB download limit")
                chunks.append(chunk)
    except ReferenceImportError:
        raise
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            raise ReferenceImportError("reference image redirects are not allowed") from exc
        raise ReferenceImportError(f"reference image request failed with HTTP {exc.code}") from exc
    except (URLError, OSError, ValueError) as exc:
        raise ReferenceImportError(f"reference image request failed: {type(exc).__name__}") from exc
    data = b"".join(chunks)
    if not data:
        raise ReferenceImportError("reference image response was empty")
    if content_length is not None and content_length != len(data):
        raise ReferenceImportError("reference image length did not match the response header")
    return DownloadPayload(
        data=data,
        content_type=content_type,
        final_url=final_url,
        content_length=content_length,
    )


BinaryTransport = Callable[[str, float, int], DownloadPayload]


def _validate_commons_record(asset: ReferenceAsset) -> None:
    if asset.provider != "wikimedia-commons" or asset.source_type != "provider-search":
        raise ReferenceImportError("only Wikimedia Commons search results can be downloaded")

    def commons_filename(url: str, *, allow_thumbnail_prefix: bool) -> str:
        media = urlsplit(url)
        if (
            media.scheme != "https"
            or media.hostname not in COMMONS_MEDIA_HOSTS
            or media.netloc not in COMMONS_MEDIA_HOSTS.union({f"{host}:443" for host in COMMONS_MEDIA_HOSTS})
            or media.username
            or media.password
            or media.query
            or media.fragment
            or not media.path.startswith("/wikipedia/commons/")
        ):
            raise ReferenceImportError("Wikimedia media URL did not pass the fixed-host policy")
        filename = unquote(Path(media.path).name).replace(" ", "_").casefold()
        if allow_thumbnail_prefix:
            filename = re.sub(r"^\d+px-", "", filename)
        if not filename:
            raise ReferenceImportError("Wikimedia media URL is missing a filename")
        return filename

    downloaded_filename = commons_filename(asset.uri, allow_thumbnail_prefix=True)
    if not asset.source_url:
        raise ReferenceImportError("Wikimedia reference is missing its source page")
    source = urlsplit(asset.source_url)
    if (
        source.scheme != "https"
        or source.hostname != COMMONS_SOURCE_HOST
        or source.netloc not in {COMMONS_SOURCE_HOST, f"{COMMONS_SOURCE_HOST}:443"}
        or source.username
        or source.password
        or not source.path.startswith("/wiki/File:")
    ):
        raise ReferenceImportError("Wikimedia reference has an invalid source page")
    source_filename = unquote(source.path.removeprefix("/wiki/File:")).replace(" ", "_").casefold()
    if not source_filename or source_filename != downloaded_filename:
        raise ReferenceImportError("Wikimedia media URL does not match its source page")
    if asset.original_uri:
        original_filename = commons_filename(asset.original_uri, allow_thumbnail_prefix=False)
        if original_filename != source_filename:
            raise ReferenceImportError("Wikimedia original image URL does not match its source page")
    if not supports_reference_import_license(asset.license_name):
        raise ReferenceImportError("reference license is missing or not on the open-license allowlist")
    creator_credit = asset.author or asset.attribution
    if not creator_credit or creator_credit.strip().casefold() == asset.license_name.strip().casefold():
        raise ReferenceImportError("reference is missing author or attribution metadata")
    if asset.license_name.lower().startswith("cc"):
        if not asset.license_url:
            raise ReferenceImportError("Creative Commons reference is missing its license URL")
        license_url = urlsplit(asset.license_url)
        if license_url.hostname not in {"creativecommons.org", "www.creativecommons.org"}:
            raise ReferenceImportError("Creative Commons license URL has an unexpected host")
        normalized_license = asset.license_name.strip().lower()
        if normalized_license.startswith("cc by-sa "):
            version = normalized_license.removeprefix("cc by-sa ")
            expected_path = f"/licenses/by-sa/{version}/"
        elif normalized_license.startswith("cc by "):
            version = normalized_license.removeprefix("cc by ")
            expected_path = f"/licenses/by/{version}/"
        elif normalized_license.startswith("cc0"):
            expected_path = "/publicdomain/zero/1.0/"
        else:
            expected_path = ""
        license_path = license_url.path.rstrip("/") + "/"
        if expected_path and not license_path.startswith(expected_path):
            raise ReferenceImportError("Creative Commons license name and URL do not match")


def _offline_source(asset: ReferenceAsset) -> Path:
    if asset.provider != "offline-example" or asset.source_type != "offline-example":
        raise ReferenceImportError("reference provider is not importable")
    parsed = urlsplit(asset.uri)
    if parsed.scheme != "example" or parsed.netloc != "figureflow":
        raise ReferenceImportError("offline reference URI is not a FigureFlow example")
    candidate = (ROOT / parsed.path.lstrip("/")).resolve()
    examples = (ROOT / "examples").resolve()
    try:
        candidate.relative_to(examples)
    except ValueError as exc:
        raise ReferenceImportError("offline reference escaped the examples directory") from exc
    if not candidate.is_file():
        raise ReferenceImportError("offline reference image is missing")
    if candidate.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise ReferenceImportError("offline reference image exceeds the 12 MB import limit")
    return candidate


def _load_payload(
    asset: ReferenceAsset,
    *,
    transport: BinaryTransport,
) -> tuple[DownloadPayload, bool]:
    if asset.provider == "offline-example":
        source = _offline_source(asset)
        data = source.read_bytes()
        suffix_mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(source.suffix.lower(), "application/octet-stream")
        return DownloadPayload(data=data, content_type=suffix_mime, final_url=asset.uri), False
    _validate_commons_record(asset)
    payload = transport(asset.uri, DOWNLOAD_TIMEOUT_SECONDS, MAX_DOWNLOAD_BYTES)
    if payload.final_url != asset.uri:
        raise ReferenceImportError("reference image redirects are not allowed")
    return payload, True


def _normalize_image(
    payload: DownloadPayload,
    destination: Path,
    *,
    declared_mime_type: str | None,
    declared_width_px: int | None,
    declared_height_px: int | None,
    allow_thumbnail_scaling: bool,
) -> tuple[int, int, str, str]:
    content_type = payload.content_type.split(";", 1)[0].strip().lower()
    if content_type not in set(ALLOWED_IMAGE_FORMATS.values()):
        raise ReferenceImportError("reference response content type is not an allowed raster image")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload.data)) as probe:
                width, height = probe.size
                image_format = str(probe.format or "").upper()
                if min(width, height) < MIN_IMAGE_DIMENSION:
                    raise ReferenceImportError("reference image is too small for layout use")
                if max(width, height) > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
                    raise ReferenceImportError("reference image dimensions exceed the safety limit")
                expected_mime = ALLOWED_IMAGE_FORMATS.get(image_format)
                if expected_mime != content_type:
                    raise ReferenceImportError("reference image bytes do not match the declared content type")
                if declared_mime_type and declared_mime_type != expected_mime:
                    raise ReferenceImportError("reference image bytes do not match search metadata")
                if declared_width_px is not None and declared_height_px is not None:
                    if allow_thumbnail_scaling:
                        declared_aspect = declared_width_px / declared_height_px
                        actual_aspect = width / height
                        scale_x = width / declared_width_px
                        scale_y = height / declared_height_px
                        if (
                            abs(actual_aspect / declared_aspect - 1.0) > 0.015
                            or abs(scale_x / scale_y - 1.0) > 0.015
                            or not 0.75 <= scale_x <= 1.25
                        ):
                            raise ReferenceImportError("reference image dimensions do not match search metadata")
                    elif (declared_width_px, declared_height_px) != (width, height):
                        raise ReferenceImportError("reference image dimensions changed after search")
                elif declared_width_px is not None and (
                    (not allow_thumbnail_scaling and declared_width_px != width)
                    or (allow_thumbnail_scaling and not 0.75 <= width / declared_width_px <= 1.25)
                ):
                    raise ReferenceImportError("reference image width does not match search metadata")
                elif declared_height_px is not None and (
                    (not allow_thumbnail_scaling and declared_height_px != height)
                    or (allow_thumbnail_scaling and not 0.75 <= height / declared_height_px <= 1.25)
                ):
                    raise ReferenceImportError("reference image height does not match search metadata")
                probe.verify()
            with Image.open(io.BytesIO(payload.data)) as decoded:
                oriented = ImageOps.exif_transpose(decoded)
                normalized = oriented.convert("RGBA" if "A" in oriented.getbands() else "RGB")
                normalized.load()
    except ReferenceImportError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError) as exc:
        raise ReferenceImportError("reference image could not be decoded safely") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.png")
    try:
        normalized.save(temporary, format="PNG", optimize=True)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    normalized_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
    return normalized.width, normalized.height, expected_mime, normalized_sha256


def _portable_result(result: ReferenceImportResult, run_dir: Path) -> dict[str, object]:
    payload = asdict(result)
    for field in ("source_path", "manifest_path"):
        payload[field] = Path(str(payload[field])).resolve().relative_to(run_dir.resolve()).as_posix()
    return payload


def materialize_reference_assets(
    assets: Sequence[ReferenceAsset],
    run_dir: Path,
    *,
    selected_ids: Sequence[str],
    transport: BinaryTransport = _fixed_host_download,
) -> list[ReferenceImportResult]:
    """Import up to three explicitly selected, validated references into ``run_dir``."""
    ordered_ids = list(dict.fromkeys(selected_ids))
    if len(ordered_ids) > MAX_IMPORTS:
        raise ReferenceImportError(f"at most {MAX_IMPORTS} reference images may be imported per run")
    if not ordered_ids:
        return []
    by_id = {asset.id: asset for asset in assets}
    if len(by_id) != len(assets):
        raise ReferenceImportError("reference asset IDs must be unique")
    missing = [reference_id for reference_id in ordered_ids if reference_id not in by_id]
    if missing:
        raise ReferenceImportError("selected reference was not present in the validated search results")

    results: list[ReferenceImportResult] = []
    for reference_id in ordered_ids:
        asset = by_id[reference_id]
        payload, network_fetched = _load_payload(asset, transport=transport)
        destination_dir = run_dir / "references" / asset.id
        source_path = destination_dir / "source.png"
        width, height, decoded_mime, normalized_sha256 = _normalize_image(
            payload,
            source_path,
            declared_mime_type=asset.declared_mime_type,
            declared_width_px=asset.declared_width_px,
            declared_height_px=asset.declared_height_px,
            allow_thumbnail_scaling=asset.original_uri is not None,
        )
        response_sha256 = hashlib.sha256(payload.data).hexdigest()
        manifest_path = destination_dir / "provenance.json"
        result = ReferenceImportResult(
            id=asset.id,
            title=asset.title,
            provider=asset.provider,
            source_path=str(source_path),
            manifest_path=str(manifest_path),
            source_url=asset.source_url,
            source_uri=asset.uri,
            original_uri=asset.original_uri,
            author=asset.author,
            license_name=asset.license_name,
            license_url=asset.license_url,
            attribution=asset.attribution,
            media_type=decoded_mime,
            width_px=width,
            height_px=height,
            bytes_received=len(payload.data),
            response_sha256=response_sha256,
            normalized_sha256=normalized_sha256,
            embedded_metadata_removed=True,
        )
        manifest = _portable_result(result, run_dir)
        manifest["schema_version"] = 1
        manifest["network_fetched"] = network_fetched
        manifest["redirects_allowed"] = False
        manifest["download_host"] = urlsplit(asset.uri).hostname if network_fetched else None
        manifest["max_download_bytes"] = MAX_DOWNLOAD_BYTES
        manifest["max_image_pixels"] = MAX_IMAGE_PIXELS
        manifest["license_check"] = (
            "open-license-metadata-allowlist" if network_fetched else "repository-bundled-example"
        )
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(result)
    return results


def public_reference_import_records(
    results: Sequence[ReferenceImportResult],
    run_dir: Path,
) -> list[Mapping[str, object]]:
    """Return manifest-ready records with only run-relative local paths."""
    return [_portable_result(result, run_dir) for result in results]
