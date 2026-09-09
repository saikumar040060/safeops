"""Request correlation IDs.

Accepts an incoming `X-Request-ID` only if it looks safe (bounded length,
alphanumeric plus `-`/`_`) -- an attacker-supplied header can otherwise be
used to inject newlines/control characters into logs or smuggle an
oversized value through. Anything else is replaced with a freshly
generated id, so every request always has exactly one well-formed id
whether or not the caller supplied one.
"""

import re
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_execution_id_var: ContextVar[str | None] = ContextVar("execution_id", default=None)
_agent_id_var: ContextVar[str | None] = ContextVar("agent_id", default=None)


def get_request_id() -> str:
    return _request_id_var.get()


def set_execution_context(execution_id: str | None = None, agent_id: str | None = None) -> None:
    """Best-effort: lets a request handler attach an execution/agent id to
    everything it logs for the rest of this request, without threading the
    values through every function signature."""
    if execution_id is not None:
        _execution_id_var.set(execution_id)
    if agent_id is not None:
        _agent_id_var.set(agent_id)


def get_execution_id() -> str | None:
    return _execution_id_var.get()


def get_agent_id() -> str | None:
    return _agent_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex

        request_id_token = _request_id_var.set(request_id)
        execution_id_token = _execution_id_var.set(None)
        agent_id_token = _agent_id_var.set(None)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(request_id_token)
            _execution_id_var.reset(execution_id_token)
            _agent_id_var.reset(agent_id_token)

        response.headers["X-Request-ID"] = request_id
        return response
