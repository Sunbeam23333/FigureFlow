from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from demo_core.model_policy import ModelCallLimitError, ModelPolicyError, SolGateway


class FakeResponses:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def gateway(log_dir: Path, response, **kwargs):
    responses = FakeResponses(response)
    return SolGateway(SimpleNamespace(responses=responses), log_dir, **kwargs), responses


class ModelPolicyTests(unittest.TestCase):
    def test_exact_contract_effort_and_sdk_response_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_items = [
                SimpleNamespace(type="reasoning", id="r1"),
                SimpleNamespace(type="message", id="m1"),
            ]
            response = SimpleNamespace(
                id="resp_1",
                model="gpt-5.6-sol",
                usage={"input_tokens": 12},
                output=output_items,
            )
            policy, fake = gateway(Path(temporary), response, reasoning_effort="xhigh")
            returned = policy.create(
                stage="review",
                instructions="inspect",
                input="full context",
                tools=[{"type": "x"}],
            )
            self.assertIs(returned, response)
            self.assertEqual(policy.output_items, output_items)
            self.assertEqual(fake.calls[0]["model"], "gpt-5.6-sol")
            self.assertEqual(fake.calls[0]["reasoning"], {"effort": "xhigh"})
            self.assertIs(fake.calls[0]["store"], False)
            self.assertEqual(policy.records[0]["identity_status"], "reported_match")
            self.assertEqual(policy.pinned_reported_model, "gpt-5.6-sol")

    def test_same_snapshot_across_multiple_steps_is_pinned_and_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = "gpt-5.6-sol-2026-07-09"
            responses = FakeResponses({"id": "one", "model": snapshot, "output": []})
            policy = SolGateway(SimpleNamespace(responses=responses), temporary)
            policy.create(stage="plan", instructions="i", input="x")
            responses.response = {"id": "two", "model": snapshot, "output": []}
            policy.create(stage="review", instructions="i", input="y")
            self.assertEqual(policy.pinned_reported_model, snapshot)
            self.assertEqual([row["identity_status"] for row in policy.records], ["reported_snapshot"] * 2)

    def test_different_snapshot_date_after_pin_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            responses = FakeResponses({"model": "gpt-5.6-sol-2026-07-09", "output": []})
            policy = SolGateway(SimpleNamespace(responses=responses), temporary)
            policy.create(stage="one", instructions="i", input="x")
            responses.response = {"model": "gpt-5.6-sol-2026-07-10", "output": []}
            with self.assertRaises(ModelPolicyError):
                policy.create(stage="two", instructions="i", input="y")
            self.assertEqual(policy.records[-1]["identity_status"], "reported_changed_after_pin")

    def test_other_family_and_invalid_snapshot_date_are_rejected(self) -> None:
        for reported in ("gpt-5.6-terra-2026-07-09", "gpt-5.6-sol-2026-02-30"):
            with self.subTest(reported=reported), tempfile.TemporaryDirectory() as temporary:
                policy, _ = gateway(Path(temporary), {"model": reported, "output": []})
                with self.assertRaises(ModelPolicyError):
                    policy.create(stage="plan", instructions="i", input="x")

    def test_missing_model_before_pin_is_unknown_but_after_pin_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            responses = FakeResponses({"id": "unknown", "output": []})
            policy = SolGateway(SimpleNamespace(responses=responses), temporary)
            policy.create(stage="unknown", instructions="i", input="x")
            self.assertEqual(policy.records[-1]["identity_status"], "identity_unreported")
            responses.response = {"model": "gpt-5.6-sol", "output": []}
            policy.create(stage="pin", instructions="i", input="x")
            responses.response = {"output": []}
            with self.assertRaises(ModelPolicyError):
                policy.create(stage="missing", instructions="i", input="x")

    def test_log_counts_exception_safety_and_call_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake = FakeResponses(error=RuntimeError("token=do-not-log"))
            policy = SolGateway(SimpleNamespace(responses=fake), temporary, max_calls=1)
            with self.assertRaisesRegex(RuntimeError, "do-not-log"):
                policy.create(stage="plan", instructions="rules", input="paper")
            with self.assertRaises(ModelCallLimitError):
                policy.create(stage="again", instructions="rules", input="paper")
            row = json.loads(Path(temporary, "model_calls.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["exception_type"], "RuntimeError")
            self.assertNotIn("do-not-log", json.dumps(row))
            self.assertEqual(len(fake.calls), 1)
