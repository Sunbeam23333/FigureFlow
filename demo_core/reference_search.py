"""Pluggable, metadata-only visual-reference search for FigureFlow.

The built-in user-URL provider records links without fetching them. The optional
Wikimedia Commons provider calls one fixed public API endpoint and returns source,
author, and license metadata; it never downloads image bytes into the renderer.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .schemas import ReferenceAsset


WIKIMEDIA_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_RASTER_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


class ReferenceSearchError(RuntimeError):
    """A user-actionable provider or response error."""


@dataclass(frozen=True)
class ReferenceSearchRequest:
    """A bounded search request shared by every reference provider."""

    query: str
    limit: int = 4
    user_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.query.strip()) > 500:
            raise ValueError("reference query must be 500 characters or fewer")
        if not 1 <= self.limit <= 8:
            raise ValueError("reference search limit must be between 1 and 8")
        if len(self.user_urls) > 8:
            raise ValueError("at most eight user reference URLs are allowed")


class ReferenceProvider(Protocol):
    """Provider contract; implementations return metadata, never renderer code."""

    name: str

    def search(self, request: ReferenceSearchRequest) -> list[ReferenceAsset]: ...


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def _clean_markup(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", html.unescape(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:500] or None


def _metadata_value(metadata: Mapping[str, Any], key: str) -> str | None:
    item = metadata.get(key)
    if isinstance(item, Mapping):
        value = item.get("value")
        return str(value) if value is not None else None
    return str(item) if item is not None else None


def _absolute_https(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("//"):
        return "https:" + value
    return value


def _fetch_json(url: str, timeout: float) -> Mapping[str, Any]:
    request = Request(url, headers={"User-Agent": "FigureFlow/0.1 reference-metadata"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - the endpoint is fixed by the provider
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ReferenceSearchError("reference provider response exceeded the 2 MB limit")
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ReferenceSearchError("reference provider returned a non-object response")
    return decoded


JsonTransport = Callable[[str, float], Mapping[str, Any]]


class OfflineExampleProvider:
    """Return a portable repository example without network access."""

    name = "offline-example"

    def search(self, request: ReferenceSearchRequest) -> list[ReferenceAsset]:
        return [
            ReferenceAsset(
                id="offline-figureflow-workflow",
                title="FigureFlow bundled synthetic workflow example",
                uri="example://figureflow/examples/figureflow_workflow.png",
                source_type="offline-example",
                provider=self.name,
                media_type="image",
                attribution="Bundled synthetic-demo reference; no network request was made.",
            )
        ][: request.limit]


class UserURLProvider:
    """Validate and record user URLs without downloading or previewing them."""

    name = "user-url"

    def search(self, request: ReferenceSearchRequest) -> list[ReferenceAsset]:
        assets: list[ReferenceAsset] = []
        for raw_url in request.user_urls[: request.limit]:
            url = raw_url.strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("user reference URLs must use http or https")
            if parsed.username or parsed.password:
                raise ValueError("user reference URLs may not contain credentials")
            # Signed query strings often carry access tokens. The metadata-only
            # provider does not need them, so never persist them in a public run.
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            host = parsed.hostname or "reference"
            assets.append(
                ReferenceAsset(
                    id=_stable_id("url", url),
                    title=f"User-provided reference from {host}",
                    uri=url,
                    source_url=url,
                    source_type="user-url",
                    provider=self.name,
                    media_type="image",
                    attribution="User-provided URL; license and reuse rights require review.",
                )
            )
        return assets


class WikimediaCommonsProvider:
    """Search Wikimedia Commons through its fixed MediaWiki metadata endpoint."""

    name = "wikimedia-commons"

    def __init__(self, *, transport: JsonTransport = _fetch_json, timeout: float = 15.0) -> None:
        self._transport = transport
        self._timeout = timeout

    def search(self, request: ReferenceSearchRequest) -> list[ReferenceAsset]:
        query = request.query.strip()
        if not query:
            raise ReferenceSearchError("Wikimedia Commons search requires a query")
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrsearch": query,
            "gsrlimit": str(request.limit),
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
        }
        endpoint = WIKIMEDIA_COMMONS_API + "?" + urlencode(params)
        try:
            payload = self._transport(endpoint, self._timeout)
        except ReferenceSearchError:
            raise
        except Exception as exc:
            raise ReferenceSearchError(f"Wikimedia Commons metadata request failed: {type(exc).__name__}") from exc
        if payload.get("error"):
            raise ReferenceSearchError("Wikimedia Commons returned an API error")
        query_payload = payload.get("query", {})
        pages = query_payload.get("pages", []) if isinstance(query_payload, Mapping) else []
        if not isinstance(pages, list):
            raise ReferenceSearchError("Wikimedia Commons returned an unexpected page list")

        assets: list[ReferenceAsset] = []
        for page in pages:
            if not isinstance(page, Mapping):
                continue
            image_info = page.get("imageinfo")
            if not isinstance(image_info, list) or not image_info or not isinstance(image_info[0], Mapping):
                continue
            info = image_info[0]
            uri = info.get("url")
            if not isinstance(uri, str):
                continue
            if info.get("mime") not in ALLOWED_RASTER_MIME_TYPES:
                continue
            metadata = info.get("extmetadata", {})
            metadata = metadata if isinstance(metadata, Mapping) else {}
            title = str(page.get("title", "Wikimedia Commons reference")).removeprefix("File:")
            source_url = info.get("descriptionurl") if isinstance(info.get("descriptionurl"), str) else None
            page_id = str(page.get("pageid", _stable_id("page", uri)))
            author = _clean_markup(_metadata_value(metadata, "Artist"))
            license_name = _clean_markup(_metadata_value(metadata, "LicenseShortName"))
            license_url = _absolute_https(_metadata_value(metadata, "LicenseUrl"))
            credit = _clean_markup(_metadata_value(metadata, "Credit"))
            attribution = credit or " · ".join(value for value in (author, license_name) if value) or None
            if not source_url or not license_name:
                continue
            try:
                asset = ReferenceAsset(
                    id=f"wm-{re.sub(r'[^a-z0-9._-]+', '-', page_id.lower()).strip('-')}",
                    title=title[:180],
                    uri=uri,
                    source_url=source_url,
                    source_type="provider-search",
                    provider=self.name,
                    media_type="image",
                    author=author[:240] if author else None,
                    license_name=license_name[:120] if license_name else None,
                    license_url=license_url,
                    attribution=attribution[:500] if attribution else None,
                )
            except ValueError:
                continue
            assets.append(asset)
            if len(assets) >= request.limit:
                break
        return assets


ProviderFactory = Callable[[], ReferenceProvider]
_PROVIDERS: dict[str, ProviderFactory] = {
    OfflineExampleProvider.name: OfflineExampleProvider,
    UserURLProvider.name: UserURLProvider,
    WikimediaCommonsProvider.name: WikimediaCommonsProvider,
}


def register_reference_provider(name: str, factory: ProviderFactory, *, replace: bool = False) -> None:
    """Register a trusted provider factory without changing FigureFlow core code."""
    if not PROVIDER_NAME.fullmatch(name):
        raise ValueError("provider names must be lowercase safe identifiers")
    if name in _PROVIDERS and not replace:
        raise ValueError(f"reference provider already registered: {name}")
    _PROVIDERS[name] = factory


def available_reference_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def search_references(
    query: str,
    *,
    provider: str = OfflineExampleProvider.name,
    limit: int = 4,
    user_urls: Sequence[str] = (),
) -> list[ReferenceAsset]:
    """Run one explicit provider; no provider performs implicit image downloads."""
    try:
        implementation = _PROVIDERS[provider]()
    except KeyError as exc:
        choices = ", ".join(available_reference_providers())
        raise ReferenceSearchError(f"unknown reference provider {provider!r}; choose from: {choices}") from exc
    request = ReferenceSearchRequest(query=query, limit=limit, user_urls=tuple(user_urls))
    results = implementation.search(request)
    if len(results) > limit:
        raise ReferenceSearchError("reference provider exceeded the requested result limit")
    return [ReferenceAsset.model_validate(asset) for asset in results]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--provider", choices=available_reference_providers(), default="offline-example")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--url", action="append", default=[], dest="user_urls")
    args = parser.parse_args()
    assets = search_references(
        args.query,
        provider=args.provider,
        limit=args.limit,
        user_urls=args.user_urls,
    )
    print(json.dumps([asset.model_dump() for asset in assets], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
