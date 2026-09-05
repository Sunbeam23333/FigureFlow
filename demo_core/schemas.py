"""Strict, renderer-safe schemas for FigureFlow planning."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EvidenceStatus = Literal[
    "measured",
    "implemented",
    "simulation",
    "forecast",
    "illustrative",
    "synthetic-demo",
    "failed-gate",
]
LayoutFamily = Literal["ribbon", "bowtie", "dual-rail"]
LayoutPreset = Literal["standard", "presentation-spacious"]
ThemeName = Literal["academic-audit", "gpu-green-tech"]
AccentName = Literal["blue", "teal", "orange", "violet", "navy"]
ReferenceSource = Literal["offline-example", "user-url", "provider-search"]
ReferenceMediaType = Literal["image", "webpage", "document"]
RasterMimeType = Literal["image/jpeg", "image/png", "image/webp"]
OPEN_REFERENCE_LICENSE = re.compile(
    r"^(?:CC0(?: 1\.0)?|Public domain|CC BY(?:-SA)? [1-9](?:\.\d)?)$",
    re.IGNORECASE,
)
AssetKey = Literal[
    "layout_planner",
    "icon_factory",
    "chroma_matte",
    "vector_typeset",
    "qa_export",
    "gpu_server",
    "robot_inspection",
    "data",
    "process",
    "decision",
    "store",
    "output",
]


def supports_reference_import_license(value: str | None) -> bool:
    """Return whether a provider license is on the automatic-import allowlist."""
    return bool(value and OPEN_REFERENCE_LICENSE.fullmatch(value.strip()))


def validate_reference_uri(value: str) -> str:
    """Accept portable reference URIs while discarding URL-borne secrets.

    Reference URLs are provenance metadata, not fetch instructions. Query strings
    are therefore unnecessary and unsafe to persist because signed URLs commonly
    carry access tokens. Fragments are likewise non-portable and are removed.
    """
    parsed = urlsplit(value.strip())
    if parsed.scheme == "example":
        if not parsed.netloc or not parsed.path:
            raise ValueError("example reference URIs require a namespace and path")
    elif parsed.scheme in {"http", "https"}:
        if not parsed.netloc:
            raise ValueError("reference URLs require a host")
        if parsed.username or parsed.password:
            raise ValueError("reference URLs may not contain credentials")
    else:
        raise ValueError("reference URIs must use example, http, or https")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class ReferenceAsset(BaseModel):
    """Portable metadata for a visual reference.

    The deterministic renderer never fetches these URLs.  A separate allowlisted
    importer may materialize an explicitly selected Commons record into the run
    directory after validating its host, license metadata, bytes, and dimensions.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str = Field(min_length=2, max_length=180)
    uri: str = Field(min_length=8, max_length=2048)
    original_uri: str | None = Field(default=None, max_length=2048)
    source_type: ReferenceSource
    provider: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    media_type: ReferenceMediaType = "image"
    source_url: str | None = Field(default=None, max_length=2048)
    author: str | None = Field(default=None, max_length=240)
    license_name: str | None = Field(default=None, max_length=120)
    license_url: str | None = Field(default=None, max_length=2048)
    attribution: str | None = Field(default=None, max_length=500)
    declared_mime_type: RasterMimeType | None = None
    declared_width_px: int | None = Field(default=None, ge=1, le=100_000)
    declared_height_px: int | None = Field(default=None, ge=1, le=100_000)
    used_in_layout: bool = False

    @field_validator("uri", "original_uri", "source_url", "license_url")
    @classmethod
    def validate_uri_fields(cls, value: str | None) -> str | None:
        return validate_reference_uri(value) if value is not None else None


def display_units(value: str) -> int:
    """Approximate rendered width: CJK/full-width glyphs count as two units."""
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in value)


class StagePlan(BaseModel):
    """One semantic stage in the final figure."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=2, max_length=18)
    subtitle: str = Field(min_length=2, max_length=40)
    body: list[str] = Field(default_factory=list, max_length=3)
    accent: AccentName = "blue"
    asset_key: AssetKey = "process"
    asset_prompt: str | None = Field(default=None, max_length=700)
    evidence_status: EvidenceStatus = "illustrative"

    @field_validator("title")
    @classmethod
    def validate_title_width(cls, value: str) -> str:
        if display_units(value) > 24:
            raise ValueError("stage title must be 24 display units or fewer")
        return value

    @field_validator("subtitle")
    @classmethod
    def validate_subtitle_width(cls, value: str) -> str:
        if display_units(value) > 28:
            raise ValueError("stage subtitle must be 28 display units or fewer")
        return value

    @field_validator("body")
    @classmethod
    def validate_body(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if any(display_units(value) > 24 for value in cleaned):
            raise ValueError("stage body lines must be 24 display units or fewer")
        return cleaned


class FigurePlan(BaseModel):
    """Structured output contract shared by GPT planning and deterministic rendering."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=4, max_length=42)
    takeaway: str = Field(min_length=8, max_length=90)
    layout_family: LayoutFamily = "ribbon"
    layout_preset: LayoutPreset = "standard"
    theme: ThemeName = "academic-audit"
    reference_assets: list[ReferenceAsset] = Field(default_factory=list, max_length=8)
    evidence_status: EvidenceStatus
    status_label: str = Field(min_length=3, max_length=36)
    stages: list[StagePlan] = Field(min_length=3, max_length=6)
    gates: list[str] = Field(default_factory=list, max_length=5)
    caption: str = Field(min_length=8, max_length=220)
    warnings: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("title")
    @classmethod
    def validate_title_width(cls, value: str) -> str:
        if display_units(value) > 60:
            raise ValueError("figure title must be 60 display units or fewer")
        return value

    @field_validator("status_label")
    @classmethod
    def validate_status_width(cls, value: str) -> str:
        if display_units(value) > 30:
            raise ValueError("status label must be 30 display units or fewer")
        return value

    @field_validator("gates")
    @classmethod
    def validate_gates(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if any(display_units(value) > 20 for value in cleaned):
            raise ValueError("gate labels must be 20 display units or fewer")
        return cleaned

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if any(len(value) > 80 for value in cleaned):
            raise ValueError("warnings must be 80 characters or fewer")
        return cleaned

    @model_validator(mode="after")
    def validate_unique_stages(self) -> "FigurePlan":
        titles = [stage.title for stage in self.stages]
        if len(set(titles)) != len(titles):
            raise ValueError("stage titles must be unique")
        asset_keys = [stage.asset_key for stage in self.stages]
        if len(set(asset_keys)) != len(asset_keys):
            raise ValueError("each stage must use a distinct semantic asset key")
        statuses = {stage.evidence_status for stage in self.stages}
        if self.evidence_status == "measured" and statuses != {"measured"}:
            raise ValueError("an overall measured figure requires every stage to be measured")
        if self.evidence_status == "implemented" and not statuses.issubset({"measured", "implemented"}):
            raise ValueError("an overall implemented figure cannot contain speculative stages")
        if self.layout_preset == "presentation-spacious" and any(len(stage.body) > 2 for stage in self.stages):
            raise ValueError("presentation-spacious permits at most two body lines per stage")
        reference_ids = [asset.id for asset in self.reference_assets]
        if len(set(reference_ids)) != len(reference_ids):
            raise ValueError("reference asset ids must be unique")
        reference_uris = [asset.uri for asset in self.reference_assets]
        if len(set(reference_uris)) != len(reference_uris):
            raise ValueError("reference asset URIs must be unique")
        return self


class PlanningMetadata(BaseModel):
    """Operational metadata; never contains secrets or raw model reasoning."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["online", "offline"]
    requested_mode: Literal["auto", "online", "offline"]
    model: str | None = None
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    fallback_reason: str | None = None
