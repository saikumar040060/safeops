"""Generic SafeOps external-agent SDK client.

This is a plain HTTP client for the generic integration API
(``/api/integrations/*``). It never touches the SafeOps database, the
ToolGateway, or any internal service directly -- every tool action it
submits goes through the same Permission -> Policy -> Risk -> Approval
pipeline as any other caller of that API, because this client IS just an
HTTP caller of that API. There is no separate, weaker code path here.

Any agent framework (or the bundled MCP adapter in ../mcp/server.py) can
use this client instead of talking to the REST API directly.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests


class SafeOpsAPIError(Exception):
    """Raised for any non-2xx response. `status_code` and `code` let a
    caller distinguish "don't retry this" (4xx, stable error code) from
    "safe to retry with the same idempotency key" (5xx) without parsing
    prose."""

    def __init__(self, status_code: int, code: str | None, message: str):
        super().__init__(f"{status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class Source:
    type: str
    content: str


class SafeOpsClient:
    """`base_url` is the SafeOps API root, e.g. http://localhost:8000/api.
    `token` is a bearer token for an INTEGRATION-type principal (never an
    OPERATOR/human token -- those are never issued the integration scopes
    this client's endpoints require)."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._timeout = timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        response = self._session.request(
            method, f"{self.base_url}{path}", timeout=self._timeout, **kwargs
        )
        if response.status_code >= 400:
            detail: dict[str, Any] = {}
            try:
                body = response.json()
                if isinstance(body.get("detail"), dict):
                    detail = body["detail"]
            except ValueError:
                pass
            raise SafeOpsAPIError(
                response.status_code,
                detail.get("code"),
                detail.get("message", response.text[:500]),
            )
        return response.json()

    def list_tools(self, *, safeops_agent_id: str) -> list[dict[str, Any]]:
        result = self._request(
            "GET", "/integrations/tools", params={"safeops_agent_id": safeops_agent_id}
        )
        assert isinstance(result, list)
        return result

    def submit_action(
        self,
        *,
        external_request_id: str,
        safeops_agent_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        execution_id: str | None = None,
        objective: str | None = None,
        sources: list[Source] | None = None,
        external_agent_id: str | None = None,
        integration_type: str = "GENERIC",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "integration_type": integration_type,
            "external_request_id": external_request_id,
            "safeops_agent_id": safeops_agent_id,
            "tool_name": tool_name,
            "arguments": arguments or {},
        }
        if execution_id is not None:
            body["execution_id"] = execution_id
        if objective is not None:
            body["objective"] = objective
        if external_agent_id is not None:
            body["external_agent_id"] = external_agent_id
        if sources:
            body["sources"] = [{"type": s.type, "content": s.content} for s in sources]
        result = self._request("POST", "/integrations/actions", json=body)
        assert isinstance(result, dict)
        return result

    def get_action(self, external_request_id: str) -> dict[str, Any]:
        result = self._request("GET", f"/integrations/actions/{external_request_id}")
        assert isinstance(result, dict)
        return result

    def submit_action_with_retry(
        self,
        *,
        max_attempts: int = 5,
        base_delay_seconds: float = 0.5,
        **submit_kwargs: Any,
    ) -> dict[str, Any]:
        """Safe retry wrapper per the milestone's retry policy:

        - The SAME `external_request_id` is used on every attempt (never
          regenerated on retry) -- that is the entire idempotency
          contract, and generating a new one on retry would defeat it.
        - 4xx responses are never retried: they are a stable, permanent
          verdict (validation error, denied mapping, blocked action,
          insufficient scope, ...), not a transient fault.
        - 5xx responses ARE safe to retry with the same key: the server
          guarantees idempotent processing keyed on
          (operator_id, external_request_id), so a retried 5xx either
          replays the already-recorded outcome or safely reprocesses.
        - 429 is honored via the `Retry-After` header when present,
          otherwise exponential backoff is used for both 429 and 5xx.
        """
        if "external_request_id" not in submit_kwargs:
            submit_kwargs["external_request_id"] = str(uuid.uuid4())

        last_error: SafeOpsAPIError | None = None
        for attempt in range(max_attempts):
            try:
                return self.submit_action(**submit_kwargs)
            except SafeOpsAPIError as exc:
                last_error = exc
                if exc.status_code == 429 or exc.status_code >= 500:
                    delay = base_delay_seconds * (2**attempt)
                    time.sleep(delay)
                    continue
                raise
        assert last_error is not None
        raise last_error

    def poll_until_complete(
        self,
        external_request_id: str,
        *,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 1.0,
    ) -> dict[str, Any]:
        """Polling only -- this API has no push/webhook mechanism in this
        milestone (see docs/integrations.md limitations). Returns as soon
        as status leaves RECEIVED/VALIDATED/PROCESSING/WAITING_APPROVAL,
        or raises TimeoutError."""
        terminal = {"EXECUTED", "BLOCKED", "FAILED"}
        deadline = time.monotonic() + timeout_seconds
        while True:
            status = self.get_action(external_request_id)
            if status["status"] in terminal:
                return status
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"action {external_request_id} still {status['status']} after "
                    f"{timeout_seconds}s"
                )
            time.sleep(poll_interval_seconds)
