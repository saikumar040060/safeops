"""Regression tests for integrations/calle/agent.py.

Runs standalone (no CALL-E API, no SafeOps API, no database):

    cd apps/api && .venv/bin/pytest ../../integrations/calle/test_agent.py -q

Covers a real bug found during a live CALL-E demo: `submit_call_outcome_
to_safeops` hardcoded `"payment_id": "PAY-9003"` regardless of what
payment a given call was actually about. A live call placed about a
different payment (PAY-9004) still silently submitted a refund request
for PAY-9003 to SafeOps -- caught only because the approval request was
inspected by hand before being approved. `payment_id` is now a required
keyword argument on both `place_refund_confirmation_call` and
`submit_call_outcome_to_safeops`, sourced from the actual call scenario,
never hardcoded inside either function.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import agent  # noqa: E402
from client import SafeOpsAPIError  # noqa: E402


class _FakeSafeOpsClient:
    def __init__(self, *, raise_error: bool = False):
        self.submit_calls: list[dict[str, Any]] = []
        self._raise_error = raise_error

    def submit_action(self, **kwargs: Any) -> dict[str, Any]:
        self.submit_calls.append(kwargs)
        if self._raise_error:
            raise SafeOpsAPIError(404, "UNKNOWN_AGENT", "no such SafeOps agent")
        return {"status": "REQUIRES_APPROVAL", "approval_request_id": "approval-1"}


class _FakeCalleCalls:
    def __init__(self):
        self.create_and_wait_calls: list[dict[str, Any]] = []

    def create_and_wait(self, **kwargs: Any) -> dict[str, Any]:
        self.create_and_wait_calls.append(kwargs)
        return {"status": "completed", "structured_result": {}}


class _FakeCalleClient:
    def __init__(self):
        self.calls = _FakeCalleCalls()


def _confirmed_call_result(payment_id_mentioned: str = "PAY-9004") -> dict[str, Any]:
    return {
        "status": "completed",
        "structured_result": {
            "wants_refund": True,
            "confirmed_amount": "750.00",
            "customer_statement": f"Yes, go ahead with the refund for {payment_id_mentioned}.",
        },
    }


# ---------------------------------------------------------------------
# submit_call_outcome_to_safeops: payment_id must come from the caller,
# never be hardcoded
# ---------------------------------------------------------------------


def test_submit_call_outcome_uses_the_given_payment_id_not_a_hardcoded_one():
    client = _FakeSafeOpsClient()
    agent.submit_call_outcome_to_safeops(
        client, "agent-1", _confirmed_call_result(), payment_id="PAY-9004"
    )
    assert len(client.submit_calls) == 1
    assert client.submit_calls[0]["arguments"]["payment_id"] == "PAY-9004"


def test_submit_call_outcome_with_a_different_payment_id_uses_that_one():
    client = _FakeSafeOpsClient()
    agent.submit_call_outcome_to_safeops(
        client, "agent-1", _confirmed_call_result(), payment_id="PAY-1234"
    )
    assert client.submit_calls[0]["arguments"]["payment_id"] == "PAY-1234"


def test_submit_call_outcome_requires_payment_id_keyword():
    with pytest.raises(TypeError):
        agent.submit_call_outcome_to_safeops(
            _FakeSafeOpsClient(), "agent-1", _confirmed_call_result()
        )


def test_submit_call_outcome_no_confirmation_submits_nothing():
    client = _FakeSafeOpsClient()
    result = agent.submit_call_outcome_to_safeops(
        client,
        "agent-1",
        {"status": "completed", "structured_result": {"wants_refund": False}},
        payment_id="PAY-9004",
    )
    assert result["status"] == "NO_ACTION"
    assert client.submit_calls == []


def test_submit_call_outcome_api_error_is_curated_not_raw():
    client = _FakeSafeOpsClient(raise_error=True)
    result = agent.submit_call_outcome_to_safeops(
        client, "agent-1", _confirmed_call_result(), payment_id="PAY-9004"
    )
    assert result == {
        "status": "ERROR",
        "code": "UNKNOWN_AGENT",
        "message": "no such SafeOps agent",
    }


# ---------------------------------------------------------------------
# place_refund_confirmation_call: the task text told to the customer must
# match the payment_id/customer_id/amount actually used
# ---------------------------------------------------------------------


def test_place_call_task_mentions_the_given_payment_details():
    client = _FakeCalleClient()
    agent.place_refund_confirmation_call(
        client, "+15551234567", payment_id="PAY-9004", customer_id="CUST-1001", amount="750.00"
    )
    task = client.calls.create_and_wait_calls[0]["task"]
    assert "PAY-9004" in task
    assert "CUST-1001" in task
    assert "750.00" in task
    assert "PAY-9003" not in task


def test_place_call_with_different_details_uses_those_not_pay_9003():
    client = _FakeCalleClient()
    agent.place_refund_confirmation_call(
        client, "+15551234567", payment_id="PAY-5555", customer_id="CUST-9999", amount="42.00"
    )
    task = client.calls.create_and_wait_calls[0]["task"]
    assert "PAY-5555" in task
    assert "CUST-9999" in task
    assert "PAY-9003" not in task
    assert "CUST-1001" not in task
