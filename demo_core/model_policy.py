"""Fail-closed policy wrapper for FigureFlow's GPT-5.6-sol text calls."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any


SOL_MODEL = "gpt-5.6-sol"
DEFAULT_MAX_OUTPUT_TOKENS = 24_000
SOL_SNAPSHOT_PATTERN = re.compile(r"^gpt-5\.6-sol-(\d{4}-\d{2}-\d{2})$")


class ModelPolicyError(RuntimeError):
    """Raised when a response violates the configured model policy."""


class ModelCallLimitError(ModelPolicyError):
    """Raised before a request that would exceed the gateway call budget."""


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump())
    return str(value)


def _hash(value: object) -> str:
    encoded = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _content_counts(value: object) -> tuple[int, int]:
    """Count text characters and image items in common Responses input shapes."""
    if isinstance(value, str):
        return len(value), 0
    if isinstance(value, (list, tuple)):
        counts = [_content_counts(item) for item in value]
        return sum(item[0] for item in counts), sum(item[1] for item in counts)
    if isinstance(value, dict):
        item_type = value.get("type")
        image_count = int(item_type in {"input_image", "image_url"})
        text_count = 0
        if item_type in {"input_text", "text"} and isinstance(value.get("text"), str):
            text_count += len(value["text"])
        for key, item in value.items():
            if key == "text" and item_type in {"input_text", "text"}:
                continue
            if key in {"image_url", "file_id"} and item_type in {"input_image", "image_url"}:
                continue
            if isinstance(item, str):
                child_text, child_images = ((len(item), 0) if key == "content" else (0, 0))
            else:
                child_text, child_images = _content_counts(item)
            text_count += child_text
            image_count += child_images
        return text_count, image_count
    return 0, 0


def _reported_identity_kind(reported_model: object) -> str | None:
    if reported_model == SOL_MODEL:
        return "bare"
    if not isinstance(reported_model, str):
        return None
    match = SOL_SNAPSHOT_PATTERN.fullmatch(reported_model)
    if not match:
        return None
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return "snapshot"


class SolGateway:
    """Make auditable Responses calls under one immutable model contract.

    ``reported_match`` means only that the API response reported the requested
    model name. It cannot prove which weights an intermediary actually served.
    """

    def __init__(
        self,
        client: object,
        log_dir: str | Path,
        reasoning_effort: str = "high",
        max_calls: int = 30,
    ):
        if not reasoning_effort:
            raise ValueError("reasoning_effort must be non-empty")
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        self.client = client
        self.log_dir = Path(log_dir)
        self.log_path = self.log_dir / "model_calls.jsonl"
        self.reasoning_effort = reasoning_effort
        self.max_calls = max_calls
        self.max_output_tokens = DEFAULT_MAX_OUTPUT_TOKENS
        self.call_count = 0
        self.records: list[dict[str, object]] = []
        self.output_items: list[object] = []
        self.pinned_reported_model: str | None = None

    def _record(self, record: dict[str, object]) -> None:
        self.records.append(record)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def create(
        self,
        *,
        stage: str,
        instructions: object,
        input: object,
        tools: object | None = None,
        text: object | None = None,
        tool_choice: object | None = None,
        max_tool_calls: int | None = None,
    ) -> object:
        if self.call_count >= self.max_calls:
            raise ModelCallLimitError(f"model call limit reached ({self.max_calls})")
        self.call_count += 1
        text_characters, image_count = _content_counts(input)
        record: dict[str, object] = {
            "call_index": self.call_count,
            "stage": stage,
            "request_model": SOL_MODEL,
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
            "instructions_sha256": _hash(instructions),
            "input_sha256": _hash(input),
            "input_text_characters": text_characters,
            "input_image_count": image_count,
        }
        kwargs: dict[str, object] = {
            "model": SOL_MODEL,
            "reasoning": {"effort": self.reasoning_effort},
            "instructions": instructions,
            "input": input,
            "store": False,
            "max_output_tokens": self.max_output_tokens,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if text is not None:
            kwargs["text"] = text
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if max_tool_calls is not None:
            kwargs["max_tool_calls"] = max_tool_calls
        started = perf_counter()
        try:
            response = self.client.responses.create(**kwargs)
            reported_model = _field(response, "model")
            response_id = _field(response, "id")
            record.update(
                {
                    "reported_model": reported_model,
                    "response_id": response_id,
                    "usage": _jsonable(_field(response, "usage")),
                    "duration_ms": round((perf_counter() - started) * 1000),
                }
            )
            if reported_model is None:
                if self.pinned_reported_model is not None:
                    record.update(
                        {
                            "status": "rejected",
                            "identity_status": "identity_missing_after_pin",
                            "pinned_reported_model": self.pinned_reported_model,
                        }
                    )
                    self._record(record)
                    raise ModelPolicyError("response omitted model identity after identity pinning")
                record.update(
                    {
                        "status": "completed",
                        "identity_status": "identity_unreported",
                        "pinned_reported_model": None,
                        "identity_note": (
                            "Response omitted model identity; the requested model is not verified."
                        ),
                    }
                )
            else:
                identity_kind = _reported_identity_kind(reported_model)
                if identity_kind is None:
                    record.update({"status": "rejected", "identity_status": "reported_mismatch"})
                    self._record(record)
                    raise ModelPolicyError("response reported an invalid or different model identity")
                if self.pinned_reported_model is not None and reported_model != self.pinned_reported_model:
                    record.update(
                        {
                            "status": "rejected",
                            "identity_status": "reported_changed_after_pin",
                            "pinned_reported_model": self.pinned_reported_model,
                        }
                    )
                    self._record(record)
                    raise ModelPolicyError("response model identity changed after identity pinning")
                self.pinned_reported_model = reported_model
                record.update(
                    {
                        "status": "completed",
                        "identity_status": (
                            "reported_match" if identity_kind == "bare" else "reported_snapshot"
                        ),
                        "reported_identity_kind": identity_kind,
                        "pinned_reported_model": self.pinned_reported_model,
                        "identity_note": (
                            "Reported family or snapshot matches the request; this does not prove "
                            "intermediary-served weights."
                        ),
                    }
                )

            output = _field(response, "output", [])
            if output is not None:
                self.output_items.extend(output if isinstance(output, (list, tuple)) else [output])
            self._record(record)
            return response
        except ModelPolicyError:
            raise
        except Exception as exc:
            record.update(
                {
                    "reported_model": None,
                    "response_id": None,
                    "usage": None,
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "status": "failed",
                    "identity_status": "identity_unreported",
                    "exception_type": type(exc).__name__,
                }
            )
            self._record(record)
            raise
