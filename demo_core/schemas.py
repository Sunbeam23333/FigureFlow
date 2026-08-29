"""Strict, renderer-safe schemas for FigureFlow planning."""

from __future__ import annotations

import unicodedata
from typing import Literal

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
ThemeName = Literal["academic-audit"]
AccentName = Literal["blue", "teal", "orange", "violet", "navy"]
AssetKey = Literal[
    "layout_planner",
    "icon_factory",
    "chroma_matte",
    "vector_typeset",
    "qa_export",
    "data",
    "process",
    "decision",
    "store",
    "output",
]


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
        if display_units(value) > 44:
            raise ValueError("stage subtitle must be 44 display units or fewer")
        return value

    @field_validator("body")
    @classmethod
    def validate_body(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if any(len(value) > 42 for value in cleaned):
            raise ValueError("stage body lines must be 42 characters or fewer")
        return cleaned


class FigurePlan(BaseModel):
    """Structured output contract shared by GPT planning and deterministic rendering."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=4, max_length=42)
    takeaway: str = Field(min_length=8, max_length=90)
    layout_family: LayoutFamily = "ribbon"
    theme: ThemeName = "academic-audit"
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
